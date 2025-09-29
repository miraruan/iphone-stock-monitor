#!/usr/bin/env python3
"""
check_stock_selenium.py

说明：
- 使用 webdriver-manager + selenium 启动 headless Chrome
- 先打开 product page 建立浏览器上下文（cookies, origin 等）
- 在浏览器上下文内用 fetch 请求 fulfillment-messages （credentials: 'include'）
- 将 (status, body) 返回到 Python，解析并在有库存时发送 Telegram
- 打印 URL、HTTP 状态、响应片段（便于调试 541）
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

# 要检测的型号（显示名 -> part number）
PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A",
}

# 要检测的新加坡 Apple Store 编号（已确认）
STORES = ["R633", "R641", "R625"]

# 每个请求之间的等待秒数（防止太密集）
DELAY_BETWEEN_REQUESTS = 1.5

# 商品页面（用来建立上下文）
PRODUCT_PAGE = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"

# 可选 — 当你想把 fetch 请求模拟成某些页面的 referer/origin 时修改：
REFERER_FOR_FETCH = PRODUCT_PAGE
# --------------------------------

def send_telegram(text: str):
    """把消息发到 Telegram（如果配置了 token & chat_id）"""
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
    """创建 Chrome webdriver（使用 webdriver-manager 自动下载 chromedriver）"""
    chrome_options = Options()
    # 推荐使用 new headless mode
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1200,900")
    # 一些 site 能更好接收真实 UA
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def fetch_fulfillment_in_browser(driver, url, timeout_sec=20):
    """
    在浏览器里使用 fetch 发起请求，并把 {status, body} 返回给 Python。
    使用 execute_async_script，最后一个参数是 callback。
    """
    # 脚本：在页面内做 fetch，然后回调结果
    script = """
    const url = arguments[0];
    const timeout = arguments[1];
    const callback = arguments[arguments.length - 1];
    // 使用 fetch，并包含 credentials（cookies）
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout*1000);
    fetch(url, { method: 'GET', credentials: 'include', cache: 'no-store' , headers: {
        // 不必要时不强行覆盖太多 header，浏览器会自动附带 origin/referer/UA/cookies
    } , signal: controller.signal })
      .then(async resp => {
        clearTimeout(id);
        const text = await resp.text();
        callback({status: resp.status, body: text});
      })
      .catch(err => {
        // 返回错误信息
        callback({error: String(err)});
      });
    """

    try:
        result = driver.execute_async_script(script, url, timeout_sec)
        return result
    except Exception as e:
        return {"error": str(e)}

def parse_availability_from_json_body(body_text):
    """
    尝试解析苹果 fulfillment-messages 的 JSON body。
    返回 (has_stock: bool, summary: str)
    summary 是简短描述，最多几百字用于通知。
    """
    try:
        j = json.loads(body_text)
    except Exception:
        # 非 JSON 响应 (HTML 等)
        snippet = body_text.replace("\n"," ")[:1000]
        return False, f"(非 JSON 响应) {snippet}"

    # 常见路径： body -> content -> pickupMessage -> stores -> partsAvailability
    pickup = j.get("body", {}).get("content", {}).get("pickupMessage")
    if pickup and isinstance(pickup, dict):
        stores = pickup.get("stores") or []
        lines = []
        any_avail = False
        for s in stores:
            store_name = s.get("storeName") or s.get("retailStore", {}).get("name", "unknown")
            parts = s.get("partsAvailability") or {}
            for part_num, info in parts.items():
                # 有时 `buyability` 会告诉是否可买
                buyable = info.get("buyability", {}).get("isBuyable")
                pickup_display = info.get("pickupDisplay") or info.get("pickupSearchQuote") or ""
                lines.append(f"{store_name} - {part_num}: {pickup_display}")
                if buyable:
                    any_avail = True
        summary = "\n".join(lines)[:1200]
        return any_avail, summary

    # 备用：尝试更宽松解析
    # 检查 body->stores
    stores2 = j.get("body", {}).get("stores")
    if stores2:
        snippet = json.dumps(stores2)[:1000]
        return False, snippet

    # fallback: short JSON
    snippet = json.dumps(j)[:1000]
    return False, snippet

def main():
    print("🟢 开始（Selenium 完整浏览器 fetch -> 解析 -> Telegram）")
    driver = None
    try:
        driver = make_driver(headless=True)
        # 先打开商品页面以建立上下文（referer / origin / cookie 等）
        driver.get(PRODUCT_PAGE)
        time.sleep(5)  # 等待页面加载 JS、cookie 被建立
        print("✅ 已打开商品页面，浏览器上下文准备就绪")

        any_notifications = []

        for model_name, part_number in PARTS.items():
            for store in STORES:
                url = (
                    "https://www.apple.com/sg/shop/fulfillment-messages?"
                    f"fae=true&pl=true&mts.0=regular&mts.1=compact"
                    f"&parts.0={part_number}&searchNearby=true&store={store}"
                )
                print("\n---")
                print("请求 URL:", url)
                # 在浏览器 fetch
                res = fetch_fulfillment_in_browser(driver, url, timeout_sec=20)
                if res is None:
                    print("⚠️ fetch 返回 None")
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    continue

                if "error" in res:
                    print("❌ fetch 内部错误:", res.get("error"))
                    print("URL:", url)
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    continue

                status = res.get("status")
                body = res.get("body", "") or ""
                print("HTTP 状态码:", status)
                preview = body.replace("\n", " ")[:1000]
                print("响应片段:", preview)

                # 处理 541 和 404 等
                if status == 541:
                    print(f"⚠️ 收到 541 Server Error（Apple 拒绝）。URL: {url}")
                    # 把响应片段也打印以供排查
                    print("541 响应片段:", preview)
                    # 可选择重试或跳过
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    continue
                if status != 200:
                    print(f"⚠️ 非 200 响应: {status}. URL: {url}")
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    continue

                # 解析 JSON 并判断是否有库存
                has_stock, summary = parse_availability_from_json_body(body)
                print("解析结果 has_stock:", has_stock)
                print("解析摘要:", summary)
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
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
