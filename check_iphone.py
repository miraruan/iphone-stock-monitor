# check_iphone_dynamic.py
import requests
import os
import time
import random

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PART_NUMBER = "MFYN4X/A"
POSTAL_CODE = "018972"
APPLE_HOMEPAGE = "https://www.apple.com/sg/iphone-17-pro-max/"
STOCK_URL = f"https://www.apple.com/sg/shop/fulfillment-messages?parts.0={PART_NUMBER}&location={POSTAL_CODE}"

# 随机生成 User-Agent
def random_user_agent():
    chrome_version = f"{random.randint(100, 140)}.0.{random.randint(4000,5000)}.{random.randint(100,200)}"
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"

# 发送 Telegram 消息
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        resp = requests.post(url, data=data, timeout=10)
        print("🟢 Telegram Status code:", resp.status_code)
    except Exception as e:
        print("❌ Telegram 发送失败:", e)

# 检查库存
def check_stock():
    # 随机延迟 3-10 秒，模拟真人操作
    time.sleep(random.randint(3, 10))

    # 第一步：访问主页获取最新 cookies
    session = requests.Session()
    headers_home = {
        "User-Agent": random_user_agent(),
        "Accept-Language": "en-SG,en;q=0.9"
    }
    try:
        resp_home = session.get(APPLE_HOMEPAGE, headers=headers_home, timeout=10)
        resp_home.raise_for_status()
        print("🟢 主页访问成功，Cookies 获取完成")
    except Exception as e:
        print("❌ 主页访问失败:", e)
        return

    # 第二步：请求库存接口
    headers_stock = {
        "User-Agent": random_user_agent(),
        "Accept-Language": "en-SG,en;q=0.9",
        "Referer": APPLE_HOMEPAGE
    }
    try:
        resp = session.get(STOCK_URL, headers=headers_stock, timeout=10)
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
