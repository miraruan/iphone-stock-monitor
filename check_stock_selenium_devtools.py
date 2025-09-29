#!/usr/bin/env python3
"""
check_stock_selenium_devtools.py

说明：
- 使用 webdriver-manager + selenium 启动 Chrome（可 headless 或有头）
- 打开商品页面建立浏览器上下文
- 利用 Selenium DevTools 捕获网络请求，自动抓取 /fulfillment-messages
- 解析库存 JSON，发现可买时发送 Telegram
- 打印 URL、HTTP 状态、响应片段
"""

import os
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.devtools import network
from webdriver_manager.chrome import ChromeDriverManager

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
REFERER_FOR_FETCH = PRODUCT_PAGE
# --------------------------------

def send_telegram(text: str):
    """把消息发到 Telegram（如果配置了 token & chat_id）"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\u26A0 Telegram 未配置，跳过发送")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text}
        )
        if not resp.ok:
            print("\u274C Telegram 返回错误:", resp.status_code, resp.text)
    except Exception as e:
        print("\u274C 发送 Telegram 异常:", e)

def make_driver(headless=True):
    """创建 Chrome webdriver"""
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

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def parse_availability_from_json_body(body_text):
    """解析 fulfillment-messages 的 JSON"""
    try:
        j = json.loads(body_text)
    except Exception:
        snippet = body_text.replace("\n", " ")[:1000]
        return False, f"(解析异常) {snippet}"

    pickup = j.get("body", {}).get("content", {}).get("pickupMessage")
    if pickup and isinstance(pickup, dict):
        stores = pickup.get("stores") or []
        lines = []
        any_avail = False
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
    print("\U0001F7E2 开始（Selenium 自动捕获 /fulfillment-messages）")
    driver = None
    try:
        driver = make_driver(headless=True)
        driver.get(PRODUCT_PAGE)
        time.sleep(5)
        print("\u2705 已打开商品页面，浏览器上下文准备就绪")

        # 启用 DevTools 网络捕获
        devtools = driver.bidi_connection
        captured_responses = {}

        # 使用 DevTools 捕获 /fulfillment-messages 的响应
        def response_listener(event):
            url = event.get("response", {}).get("url", "")
            if "/fulfillment-messages" in url:
                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": event["requestId"]})
                captured_responses[url] = body.get("body", "")

        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})

        any_notifications = []

        for model_name, part_number in PARTS.items():
            for store in STORES:
                url = (
                    "https://www.apple.com/sg/shop/fulfillment-messages?"
                    f"fae=true&little=false&parts.0={part_number}&mts.0=regular&mts.1=sticky&fts=true&store={store}"
                )
                print("URL:", url)
                driver.get(url)
                time.sleep(3)  # 等待响应加载

                # 尝试获取捕获的响应
                body_text = captured_responses.get(url, "")
                has_stock, summary = parse_availability_from_json_body(body_text)
                print("has_stock:", has_stock)
                print("摘要:", summary)

                if has_stock:
                    msg = f"\u2705 库存提醒：{model_name} 可能在 {store} 有货\n{summary}\n{url}"
                    send_telegram(msg)
                    any_notifications.append(msg)

                time.sleep(DELAY_BETWEEN_REQUESTS)

        if not any_notifications:
            print("\U0001F7E2 本次未检测到可用库存。")
        print("\U0001F7E2 检查完成")
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
