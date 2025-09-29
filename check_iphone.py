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
FAIL_ALERT_THRESHOLD = 3             # 连续失败阈值，达到后发送一次告警（可调整）


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
    """
    返回说明：
      - None：请求失败（HTTP 非 200 / JSON 解析失败 / 被封等）
      - []：有效响应，但无库存
      - [msg1, msg2, ...]：有库存信息的列表
    """
    try:
        r = requests.get(CHECK_URL, headers=HEADERS, timeout=10)
        # 如果被网站通过 404 等方式阻断，会在这里抛出 HTTPError
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
        # 如果 delivery 结构意外，不要因为这个导致整个函数失败
        pass

    return results


def read_last_stock():
    if os.path.exists(LAST_STOCK_FILE):
        with open(LAST_STOCK_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None  # 第一次运行返回 None


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
    # 判断是否是手动触发（GitHub Actions 会传入 GITHUB_EVENT_NAME）
    is_manual = os.environ.get("GITHUB_EVENT_NAME", "") == "workflow_dispatch"
    if is_manual:
        send_telegram("⚡ iPhone 库存检查脚本已手动运行")

    result = check_stock()

    if result is None:
        # 请求失败（404 或解析错误等）
        fail_count = read_fail_count() + 1
        save_fail_count(fail_count)
        print(f"请求失败计数：{fail_count}")

        # 如果达到阈值，发送一次告警（提醒人工查看）
        if fail_count >= FAIL_ALERT_THRESHOLD:
            send_telegram(
                f"⚠️ iPhone 监控: 连续 {fail_count} 次请求失败（可能被封禁或网络异常）。请人工检查。"
            )
            # 为避免重复刷屏，这里可以把计数重置到 0 或减小到避免不停发告警
            save_fail_count(0)
        # **重要**：遇到请求失败**不要**覆盖 last_stock.txt，直接退出
        print("请求失败，不修改上次库存状态，等待下一次尝试。")
        exit(0)

    # 到这里说明请求成功并且 json 解析 OK
    # 清零失败计数
    save_fail_count(0)

    msgs = result  # list，可能为空
    msg_combined = "\n\n".join(msgs) if msgs else ""

    last_msg = read_last_stock()

    # 第一次运行（last_msg 为 None）时，初始化并不发送库存消息
    if last_msg is None:
        print("第一次运行，初始化库存状态（不发送库存消息）")
        save_last_stock(msg_combined)
        exit(0)

    # 如果库存消息发生变化且有库存信息时再发送（避免发送空内容）
    if msg_combined != last_msg:
        if msg_combined:
            send_telegram(msg_combined)  # 只有非空（即确实有货或可配送）才发送
            print("检测到库存变化并已发送通知")
        else:
            # msg_combined 为空，表示当前无货；我们更新记录但不发送（你想只在有货时才通知）
            print("库存从有变为无（或仍无货），更新状态但不通知")
        save_last_stock(msg_combined)
    else:
        print("库存没有变化，不重复提醒")
