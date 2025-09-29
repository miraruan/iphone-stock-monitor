#!/usr/bin/env python3
"""
check_stock_selenium_devtools.py

- 使用 Selenium + Chrome DevTools Protocol 捕获 /fulfillment-messages
- 在浏览器中执行完整页面 JS 初始化
- 抓取请求响应 JSON 并解析库存
- GitHub Actions 可直接运行
"""

import os
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager

# ---------- 配置 ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A",
}

STORES = ["R633", "R641", "R625"]

DELAY_BETWEEN_REQUESTS = 1.5

PRODUCT_PAGE = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"
# ------------------------

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

    # 开启 performance log
    caps = DesiredCapabilities.CHROME
    caps["goog:loggingPrefs"] = {"performance": "ALL"}

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options,
        desired_capabilities=caps
    )
    return driver

def parse_response_body(body_text):
    try:
        j = json.loads(body_text)
        return j
    except Exception:
        return None

def extract_stock_info(json_body):
    """
    返回 (has_stock: bool, summary: str)
    """
    pickup = json_body.get("body", {}).get("content", {}).get("pickupMessage")
    delivery = json_body.get("body", {}).get("content", {}).get("deliveryMessage")
    lines = []
    any_avail = False

    if pickup and isinstance(pickup, dict):
        stores = pickup.get("stores") or []
        for s in stores:
            store_name = s.get("storeName") or s.get("retailStore", {}).get("name", "unknown")
            parts = s.get("partsAvailability") or {}
            for part_num, info in parts.items():
                buyable = info.get("buyability", {}).get("isBuyable")
                pickup_display = info.get("pickupDisplay") or info.get("pickupSearchQuote") or ""
                lines.append(f"{store_name} - {part_num}: {pickup_display}")
                if buyable:
                    any_avail = True

    if delivery and isinstance(delivery, dict):
        for part_num, info in delivery.items():
            if not isinstance(info, dict):
                continue
            buyable = info.get("buyability", {}).get("isBuyable")
            quote = info.get("regular", {}).get("stickyMessageSTH") or info.get("compact", {}).get("quote")
            if quote:
                lines.append(f"Delivery {part_num}: {quote}")
            if buyable:
                any_avail = True

    summary = "\n".join(lines)[:1200]
    return any_avail, summary

def main():
    print("🟢 开始（Selenium + DevTools 捕获 /fulfillment-messages）")
    driver = None
    try:
        driver = make_driver(headless=True)
        driver.get(PRODUCT_PAGE)
        time.sleep(5)  # 等待页面 JS 初始化
        print("✅ 商品页面加载完成，浏览器上下文准备就绪")

        any_notifications = []

        # 循环每个型号和商店
        for model_name, part_number in PARTS.items():
            for store in STORES:
                url_substr = f"/fulfillment-messages?fae=true&pl=true&parts.0={part_number}&store={store}"
                found = False
                status = None
                body = None

                # 遍历 performance log
                logs = driver.get_log("performance")
                for entry in logs:
                    message = json.loads(entry["message"])["message"]
                    if message.get("method") == "Network.responseReceived":
                        resp_url = message["params"]["response"]["url"]
                        if url_substr in resp_url:
                            status = message["params"]["response"]["status"]
                            # 获取 body
                            request_id = message["params"]["requestId"]
                            try:
                                body_raw = driver.execute_cdp_cmd(
                                    "Network.getResponseBody", {"requestId": request_id}
                                )
                                body = body_raw.get("body")
                            except Exception as e:
                                body = f"(获取 body 出错: {e})"
                            found = True
                            break

                if not found:
                    # 如果 performance log 没捕获到，可以尝试直接访问 URL
                    full_url = (
                        "https://www.apple.com/sg/shop/fulfillment-messages?"
                        f"fae=true&pl=true&mts.0=regular&mts.1=compact"
                        f"&parts.0={part_number}&searchNearby=true&store={store}"
                    )
                    driver.get(full_url)
                    time.sleep(2)
                    body = driver.page_source
                    status = 200  # 猜测
                    print(f"⚠️ 未在 Performance Log 找到请求，尝试直接访问 URL: {full_url}")

                preview = (body or "")[:1000].replace("\n"," ")
                print("\n---")
                print(f"型号 {model_name} 店 {store}")
                print("HTTP 状态码:", status)
                print("响应片段:", preview)

                json_body = parse_response_body(body) if body else None
                if json_body:
                    has_stock, summary = extract_stock_info(json_body)
                    print("解析结果 has_stock:", has_stock)
                    print("摘要:", summary)
                    if has_stock:
                        msg = f"✅ 库存提醒：{model_name} 可能在 {store} 有货\n{summary}\nURL: {full_url}"
                        send_telegram(msg)
                        any_notifications.append(msg)
                else:
                    print("⚠️ JSON 解析失败，可能是 HTML 或错误页面")

                time.sleep(DELAY_BETWEEN_REQUESTS)

        if not any_notifications:
            print("🟢 本次未检测到可用库存。")
        print("🟢 检查完成")

    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
