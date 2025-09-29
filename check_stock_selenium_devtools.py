#!/usr/bin/env python3
"""
check_stock_selenium_devtools.py

说明：
- Selenium + Chrome DevTools Protocol 捕获网络请求
- 无头模式模拟有头（--headless=new + navigator.webdriver 等反爬处理）
- 捕获 /fulfillment-messages 请求的 JSON 响应
- 解析库存并通过 Telegram 通知
"""

import os
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.devtools.v109 import network

# ---------- 配置区域 ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A",
}

STORES = ["R633", "R641", "R625"]
DELAY_BETWEEN_REQUESTS = 1.5
PRODUCT_PAGE = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"
# --------------------------------

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(⚠️ Telegram 未配置，跳过发送")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text}
        )
        if not resp.ok:
            print("❌ Telegram 返回错误:", resp.status_code, resp.text)
    except Exception as e:
        print("❌ 发送 Telegram 异常:", e)

def make_driver(headless=True) -> WebDriver:
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1200,900")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(
        service=Service(),  # 自动使用系统 chromedriver 或 webdriver-manager
        options=chrome_options
    )

    # 无头模拟有头：去掉 navigator.webdriver
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            """
        }
    )
    return driver

def capture_fulfillment_messages(driver: WebDriver, part_number: str):
    """
    捕获浏览器发出的 /fulfillment-messages 请求
    返回列表 [(store, json_body), ...]
    """
    results = []

    # 启用网络监听
    devtools = driver.bidi_connection if hasattr(driver, 'bidi_connection') else None
    # Selenium <v4.13 可以用 execute_cdp_cmd 捕获 network
    driver.execute_cdp_cmd("Network.enable", {})

    urls_to_watch = []

    def request_will_be_sent(params):
        url = params.get("request", {}).get("url", "")
        if "/fulfillment-messages" in url and f"parts.0={part_number}" in url:
            urls_to_watch.append(url)

    driver.execute_cdp_cmd("Network.clearBrowserCache", {})
    driver.execute_cdp_cmd("Network.clearBrowserCookies", {})

    # Selenium 没有完整事件回调接口，这里直接打开页面让浏览器请求
    driver.get(PRODUCT_PAGE)
    time.sleep(5)  # 等待 JS 初始化并发起请求

    # 直接访问 /fulfillment-messages
    for store in STORES:
        url = (
            "https://www.apple.com/sg/shop/fulfillment-messages?"
            f"fae=true&little=false&parts.0={part_number}&mts.0=regular&mts.1=sticky&fts=true&store={store}"
        )
        driver.get(url)
        time.sleep(3)
        body_text = driver.find_element(By.TAG_NAME, "pre").text if driver.find_elements(By.TAG_NAME, "pre") else driver.page_source
        results.append((store, body_text))
    return results

def parse_availability(body_text: str):
    try:
        j = json.loads(body_text)
    except Exception:
        snippet = body_text.replace("\n"," ")[:1000]
        return False, f"(解析异常) {snippet}"
    pickup = j.get("body", {}).get("content", {}).get("pickupMessage")
    if pickup and isinstance(pickup, dict):
        stores = pickup.get("stores") or []
        any_avail = False
        lines = []
        for s in stores:
            store_name = s.get("storeName") or s.get("retailStore", {}).get("name", "unknown")
            parts = s.get("partsAvailability") or {}
            for part_num, info in parts.items():
                buyable = info.get("buyability", {}).get("isBuyable")
                pickup_display = info.get("pickupDisplay") or info.get("pickupSearchQuote") or ""
                lines.append(f"{store_name} - {part_num}: {pickup_display}")
                if buyable:
                    any_avail = True
        summary = "\n".join(lines)[:1200]
        return any_avail, summary
    snippet = json.dumps(j)[:1000]
    return False, snippet

def main():
    print("🟢 开始（Selenium 自动捕获 /fulfillment-messages）")
    driver = None
    try:
        driver = make_driver(headless=True)
        print("✅ 已打开商品页面，浏览器上下文准备就绪")
        any_notifications = []

        for model_name, part_number in PARTS.items():
            results = capture_fulfillment_messages(driver, part_number)
            for store, body in results:
                has_stock, summary = parse_availability(body)
                print("URL: /fulfillment-messages?parts.0=", part_number)
                print("has_stock:", has_stock)
                print("摘要:", summary)
                if has_stock:
                    msg = f"✅ 库存提醒：{model_name} 可能在 {store} 有货\n{summary}\n"
                    send_telegram(msg)
                    any_notifications.append(msg)
                time.sleep(DELAY_BETWEEN_REQUESTS)

        if not any_notifications:
            print("🟢 本次未检测到可用库存。")
        print("🟢 检查完成")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
