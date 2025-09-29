#!/usr/bin/env python3
"""
check_stock_selenium_direct.py

说明：
- Selenium 启动 headless Chrome
- 先打开 product page 建立浏览器上下文
- 直接访问 fulfillment-messages URL（浏览器本身请求）
- 抓取返回的页面内容并解析 JSON
- 有库存时发送 Telegram
"""

import os
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ---------- 配置区域 ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 要检测的型号（显示名 -> part number）
PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A",
}

# 要检测的新加坡 Apple Store 编号
STORES = ["R633", "R641", "R625"]

DELAY_BETWEEN_REQUESTS = 1.5

# 商品页面（建立浏览器上下文）
PRODUCT_PAGE = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"
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
            print("❌ Telegram 返回错误:", resp.status_code, resp.text)
    except Exception as e:
        print("❌ 发送 Telegram 异常:", e)

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
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver

def fetch_page_source(driver, url):
    """通过浏览器直接访问 URL，并获取页面内容"""
    driver.get(url)
    time.sleep(3)  # 等待 JS 执行
    return driver.page_source

def parse_availability_from_json(body_text):
    """解析 fulfillment-messages JSON"""
    try:
        j = json.loads(body_text)
    except Exception:
        snippet = body_text.replace("\n", " ")[:1000]
        return False, f"(解析异常) {snippet}"

    # 尝试 body -> content -> deliveryMessage
    delivery = j.get("body", {}).get("content", {}).get("deliveryMessage")
    if delivery:
        lines = []
        any_avail = False
        for part_num, info in delivery.items():
            buyable = info.get("isBuyable") or info.get("buyability", {}).get("isBuyable")
            if not buyable:
                continue
            if "regular" in info:
                lines.append(f"{part_num}: {info['regular'].get('stickyMessageSTH','')}")
            elif "compact" in info:
                lines.append(f"{part_num}: {info['compact'].get('quote','')}")
            any_avail = True
        summary = "\n".join(lines)[:1200]
        return any_avail, summary

    snippet = json.dumps(j)[:1000]
    return False, snippet

def main():
    print("🟢 开始（Selenium 自动访问 /fulfillment-messages）")
    driver = None
    try:
        driver = make_driver(headless=True)
        driver.get(PRODUCT_PAGE)
        time.sleep(5)
        print("✅ 已打开商品页面，浏览器上下文准备就绪")

        any_notifications = []

        for model_name, part_number in PARTS.items():
            for store in STORES:
                url = (
                    "https://www.apple.com/sg/shop/fulfillment-messages?"
                    f"fae=true&little=false&parts.0={part_number}&mts.0=regular&mts.1=sticky&fts=true"
                )
                print("\nURL:", url)
                page_source = fetch_page_source(driver, url)
                has_stock, summary = parse_availability_from_json(page_source)
                print("has_stock:", has_stock)
                print("摘要:", summary)
                if has_stock:
                    msg = f"✅ 库存提醒：{model_name} 可能在 {store} 有货\n{summary}\n{url}"
                    print("触发通知 ->", msg)
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
