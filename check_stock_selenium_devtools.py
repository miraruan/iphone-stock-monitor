#!/usr/bin/env python3
"""
check_stock_selenium.py

说明：
- 使用 webdriver-manager + selenium 启动 headless Chrome
- 打开商品页面，等待 JS 初始化
- 通过 DevTools network log 捕获页面发出的 /fulfillment-messages 请求
- 解析库存信息并在有库存时发送 Telegram
"""

import time
import json
import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ---------- 配置区域 ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A",
}

DELAY_BETWEEN_CHECKS = 1.5

# 商品页面（建立上下文）
PRODUCT_PAGE = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"
# --------------------------------

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram 未配置，跳过发送")
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

def make_driver(headless=True):
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

    # Selenium 4+ 方式开启 performance log
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver

def parse_fulfillment_from_text(text, part_number):
    any_avail = False
    summary_lines = []

    try:
        j = json.loads(text)
        pickup = j.get("body", {}).get("content", {}).get("pickupMessage")
        if pickup and isinstance(pickup, dict):
            stores_data = pickup.get("stores") or []
            for s in stores_data:
                store_name = s.get("storeName") or s.get("retailStore", {}).get("name", "unknown")
                parts = s.get("partsAvailability") or {}
                for pn, info in parts.items():
                    if pn != part_number:
                        continue
                    buyable = info.get("buyability", {}).get("isBuyable")
                    pickup_display = info.get("pickupDisplay") or info.get("pickupSearchQuote") or ""
                    summary_lines.append(f"{store_name} - {pn}: {pickup_display}")
                    if buyable:
                        any_avail = True
    except Exception as e:
        summary_lines.append(f"(解析异常) {str(e)}")

    return any_avail, "\n".join(summary_lines)[:1200]

def main():
    print("🟢 开始（Selenium 自动捕获 /fulfillment-messages）")
    driver = None
    try:
        driver = make_driver(headless=True)
        driver.get(PRODUCT_PAGE)
        time.sleep(5)  # 等待页面 JS 初始化 cookies
        print("✅ 已打开商品页面，浏览器上下文准备就绪")

        # 启动 network tracking
        driver.execute_cdp_cmd("Network.enable", {})

        seen_requests = set()
        any_notifications = []

        start_time = time.time()
        # 循环捕获请求，可以设置一个最大等待时间，例如 20 秒
        while time.time() - start_time < 20:
            logs = driver.get_log("performance")
            for entry in logs:
                try:
                    message = json.loads(entry["message"])["message"]
                    method = message.get("method")
                    if method != "Network.responseReceived":
                        continue
                    resp = message.get("params", {}).get("response", {})
                    url = resp.get("url", "")
                    if "/fulfillment-messages" not in url or url in seen_requests:
                        continue
                    seen_requests.add(url)

                    request_id = message["params"]["requestId"]
                    body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                    text = body.get("body", "")

                    # 检查每个型号
                    for model_name, part_number in PARTS.items():
                        has_stock, summary = parse_fulfillment_from_text(text, part_number)
                        print(f"URL: {url}")
                        print(f"has_stock: {has_stock}")
                        print(f"摘要: {summary}")

                        if has_stock:
                            msg = f"✅ 库存提醒：{model_name}\n{summary}\n{url}"
                            print("触发通知 ->", msg)
                            send_telegram(msg)
                            any_notifications.append(msg)

                    time.sleep(DELAY_BETWEEN_CHECKS)

                except Exception as e:
                    print("⚠️ 解析 log 异常:", e)

        if not any_notifications:
            print("🟢 本次未检测到可用库存。")
        print("🟢 检查完成")

    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
