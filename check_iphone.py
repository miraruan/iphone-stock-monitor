# check_iphone.py
import requests
import os
import time
import random

# 从 GitHub Secrets 读取
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Apple iPhone 17 Pro Max 256GB Cosmic Orange SG
PART_NUMBER = "MFYN4X/A"
POSTAL_CODE = "018972"
URL = f"https://www.apple.com/sg/shop/fulfillment-messages?parts.0={PART_NUMBER}&location={POSTAL_CODE}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
    "Referer": "https://www.apple.com/sg/iphone-17-pro-max/"
}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        resp = requests.post(url, data=data, timeout=10)
        print("🟢 Telegram Status code:", resp.status_code)
        print("🟢 Telegram Response:", resp.text)
    except Exception as e:
        print("❌ Telegram 发送失败:", e)

def check_stock():
    # 随机延迟 3-10 秒，避免被封
    time.sleep(random.randint(3, 10))
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        stores = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
        stock_available = False
        for store in stores:
            parts = store.get("partsAvailability", {})
            part = parts.get(PART_NUMBER, {})
            buyable = part.get("buyability", {}).get("isBuyable", False)
            store_name = store.get("storeName")
            if buyable:
                stock_available = True
                print(f"✅ {store_name} 有库存！")
                send_telegram(f"🍏 iPhone 17 Pro Max 256GB Cosmic Orange 有库存！\n店铺：{store_name}")
            else:
                print(f"❌ {store_name} 无库存")

        if not stock_available:
            print("ℹ️ 当前所有店铺均无库存")

    except requests.exceptions.HTTPError as e:
        print("❌ HTTPError:", e)
    except requests.exceptions.RequestException as e:
        print("❌ 请求异常:", e)
    except Exception as e:
        print("❌ 其他异常:", e)

if __name__ == "__main__":
    print("🟢 开始检查库存...")
    check_stock()
    print("🟢 检查结束")
