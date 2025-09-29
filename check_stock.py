import subprocess
import os
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# ==== 配置 ====
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A"
}

STORES = ["R633", "R641", "R625"]  # 新加坡所有店

# ==== Telegram 推送 ====
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram 配置缺失")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
        if not resp.ok:
            print("❌ Telegram 发送失败", resp.text)
    except Exception as e:
        print("❌ Telegram 发送异常", e)

# ==== Selenium 获取最新 cookie ====
def get_cookies():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange")

    selenium_cookies = driver.get_cookies()
    driver.quit()

    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in selenium_cookies])
    return cookie_str

# ==== 使用 curl 请求库存 ====
def fetch_stock_curl(part_number, store, cookie_str):
    url = f"https://www.apple.com/sg/shop/fulfillment-messages?fae=true&pl=true&mts.0=regular&mts.1=compact&parts.0={part_number}&searchNearby=true&store={store}"

    curl_cmd = [
        "curl", "-s",
        url,
        "-H", "accept: */*",
        "-H", "accept-language: en,zh-CN;q=0.9,zh;q=0.8",
        "-b", cookie_str,
        "-H", "priority: u=1, i",
        "-H", "referer: https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange",
        "-H", "sec-ch-ua: \"Chromium\";v=\"140\", \"Not=A?Brand\";v=\"24\", \"Google Chrome\";v=\"140\"",
        "-H", "sec-ch-ua-mobile: ?0",
        "-H", "sec-ch-ua-platform: \"Windows\"",
        "-H", "sec-fetch-dest: empty",
        "-H", "sec-fetch-mode: cors",
        "-H", "sec-fetch-site: same-origin",
        "-H", "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
        "-H", "x-aos-ui-fetch-call-1: 6aytv11r5t-mg58qvbu"
    ]

    result = subprocess.run(curl_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ curl 请求失败: {result.stderr}")
        return None

    try:
        return json.loads(result.stdout)
    except Exception as e:
        print(f"❌ JSON 解析失败: {e}")
        return None

# ==== 检查库存 ====
def check_stores():
    print("🟢 开始检查库存...")
    cookie_str = get_cookies()
    messages = []

    for name, part in PARTS.items():
        for store in STORES:
            print(f"🔹 检测型号 —— {name} @ {store}")
            data = fetch_stock_curl(part, store, cookie_str)
            if not data:
                print(f"❌ {name} @ {store} 请求失败")
                continue

            pickup_msg = data.get("body", {}).get("content", {}).get("pickupMessage", "")
            print(f"库存信息: {pickup_msg}")
            if "available" in pickup_msg.lower():
                messages.append(f"✅ {name} @ {store} 有库存！")

    if messages:
        send_telegram("\n".join(messages))
    else:
        print("🟢 暂无库存")
    print("🟢 检查结束\n")

if __name__ == "__main__":
    check_stores()
