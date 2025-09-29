import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import os

# Telegram 配置
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 机型和店铺列表
MODELS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A"
}
STORES = ["R633", "R641", "R625"]  # SG 实体店

# 获取 cookies
def get_cookies():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.get("https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange")

    cookies = driver.get_cookies()
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    driver.quit()
    return cookie_str

# 检查库存
def check_stock(cookie_str):
    headers = {
        "accept": "*/*",
        "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    }

    for model_name, part_number in MODELS.items():
        for store in STORES:
            url = f"https://www.apple.com/sg/shop/fulfillment-messages?fae=true&pl=true&mts.0=regular&mts.1=compact&parts.0={part_number}&searchNearby=true&store={store}"
            print(f"检测型号 —— {model_name} @ {store}")
            try:
                response = requests.get(url, headers=headers, cookies={c.split("=")[0]: c.split("=")[1] for c in cookie_str.split("; ")})
                if response.status_code == 200:
                    data = response.json()
                    pickup = data.get("body", {}).get("content", {}).get("pickupMessage", "未知")
                    print(f"库存状态: {pickup}")
                    # Telegram 通知
                    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                        requests.get(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            params={"chat_id": TELEGRAM_CHAT_ID, "text": f"{model_name} @ {store}：{pickup}"}
                        )
                else:
                    print(f"请求失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"检测异常: {e}")
            time.sleep(1)

if __name__ == "__main__":
    print("🟢 开始检查库存…")
    cookie_str = get_cookies()
    print("✅ Cookies 获取完成")
    check_stock(cookie_str)
    print("🟢 检查结束")
