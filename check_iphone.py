import os
import requests

# Apple 官网 API
CHECK_URL = "https://www.apple.com/sg/shop/fulfillment-messages?parts.0=MFYN4X/A&location=018972"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.apple.com/sg/shop/buy-iphone",
}

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
LAST_STOCK_FILE = "last_stock.txt"  # 保存上一次库存状态

def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=data, timeout=5)
        print("📩 已推送到 Telegram")
    except Exception as e:
        print("Telegram 推送失败：", e)

def check_stock():
    try:
        r = requests.get(CHECK_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        js = r.json()
    except Exception as e:
        print("请求苹果官网失败：", e)
        return []

    stores = js["body"]["content"]["pickupMessage"]["stores"]
    delivery = js["body"]["content"]["deliveryMessage"]["MFYN4X/A"]

    results = []

    # 店内库存
    for st in stores:
        info = st["partsAvailability"]["MFYN4X/A"]
        if info.get("pickupDisplay") == "available":
            results.append(
                f"✅ 店内现货: {st['storeName']}\n"
                f"地址: {st['address']['address2']}, {st['address']['postalCode']}\n"
                f"电话: {st['phoneNumber']}\n"
                f"预约链接: {st['makeReservationUrl']}"
            )

    # 配送库存
    if delivery["regular"]["buyability"]["isBuyable"]:
        date = delivery["regular"]["deliveryOptionMessages"][0]["displayName"]
        results.append(f"📦 可配送，下单预计送达: {date}")

    return results

def read_last_stock():
    if os.path.exists(LAST_STOCK_FILE):
        with open(LAST_STOCK_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None  # 第一次运行返回 None

def save_last_stock(stock_msg):
    with open(LAST_STOCK_FILE, "w", encoding="utf-8") as f:
        f.write(stock_msg)

if __name__ == "__main__":
    # 判断是否是手动触发
    is_manual = os.environ.get("GITHUB_EVENT_NAME", "") == "workflow_dispatch"

    # 手动触发先发提醒
    if is_manual:
        send_telegram("⚡ iPhone 库存检查脚本已手动运行")

    # 检查库存
    msgs = check_stock()
    msg_combined = "\n\n".join(msgs) if msgs else ""

    last_msg = read_last_stock()

    # 第一次运行或库存变化才发送消息
    if last_msg is None:
        print("第一次运行，初始化库存状态，不发送库存消息")
        save_last_stock(msg_combined)
    elif msg_combined != last_msg:
        if msg_combined:
            send_telegram(msg_combined)
        save_last_stock(msg_combined)
    else:
        print("库存没有变化，不重复提醒")
