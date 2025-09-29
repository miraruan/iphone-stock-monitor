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
LAST_STOCK_FILE = "last_stock.txt"   # 保存上一次库存状态
FAIL_COUNT_FILE = "fail_count.txt"   # 保存连续失败次数
FAIL_ALERT_THRESHOLD = 3             # 连续失败阈值，达到后发送一次告警


def send_telegram(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram 配置缺失，跳过发送：", msg)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        resp = requests.post(url, data=data, timeout=8)
        print("📩 推送结果：", resp.status_code)
    except Exception as e:
        print("Telegram 推送失败：", e)


def check_stock():
    try:
        r = requests.get(CHECK_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        js = r.json()
    except Exception as e:
        print("请求苹果官网失败或被封禁：", e)
        return None

    try:
        stores = js["body"]["content"]["pickupMessage"]["stores"]
        delivery = js["body"]["content"]["deliveryMessage"]["MFYN4X/A"]
    except Exception as e:
        print("解析 JSON 结构失败：", e)
        return None

    results = []

    # 店内库存
    for st in stores:
        info = st.get("partsAvailability", {}).get("MFYN4X/A", {})
        if info.get("pickupDisplay") == "available":
            results.append(
                f"✅ 店内现货: {st.get('storeName')}\n"
                f"地址: {st.get('address', {}).get('address2','')}, {st.get('address', {}).get('postalCode','')}\n"
                f"电话: {st.get('phoneNumber')}\n"
                f"预约链接: {st.get('makeReservationUrl')}"
            )

    # 配送库存
    try:
        if delivery.get("regular", {}).get("buyability", {}).get("isBuyable"):
            date = delivery["regular"]["deliveryOptionMessages"][0]["displayName"]
            results.append(f"📦 可配送，下单预计送达: {date}")
    except Exception:
        pass

    return results


def read_last_stock():
    if os.path.exists(LAST_STOCK_FILE):
        with open(LAST_STOCK_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def save_last_stock(stock_msg):
    with open(LAST_STOCK_FILE, "w", encoding="utf-8") as f:
        f.write(stock_msg or "")


def read_fail_count():
    if os.path.exists(FAIL_COUNT_FILE):
        try:
            with open(FAIL_COUNT_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip() or 0)
        except Exception:
            return 0
    return 0


def save_fail_count(n):
    with open(FAIL_COUNT_FILE, "w", encoding="utf-8") as f:
        f.write(str(int(n)))


if __name__ == "__main__":
    is_manual = os.environ.get("GITHUB_EVENT_NAME", "") == "workflow_dispatch"

    result = check_stock()

    if result is None:
        fail_count = read_fail_count() + 1
        save_fail_count(fail_count)
        print(f"请求失败计数：{fail_count}")

        if fail_count >= FAIL_ALERT_THRESHOLD:
            send_telegram(
                f"⚠️ iPhone 监控: 连续 {fail_count} 次请求失败（可能被封禁或网络异常）。请人工检查。"
            )
            save_fail_count(0)
        exit(0)

    save_fail_count(0)

    msgs = result
    msg_combined = "\n\n".join(msgs) if msgs else "当前无库存"

    last_msg = read_last_stock()

    # 第一次运行或者手动触发，都发送库存信息
    if last_msg is None:
        save_last_stock(msg_combined)
        send_telegram(msg_combined)
        exit(0)

    if msg_combined != last_msg:
        # 库存变化时发送
        send_telegram(msg_combined)
        save_last_stock(msg_combined)
        print("库存变化，已发送通知")
    elif is_manual:
        # 手动触发且库存未变化，也发送一次
        send_telegram(msg_combined)
        print("手动触发，库存信息已发送")
    else:
        print("库存未变化，不发送消息")
