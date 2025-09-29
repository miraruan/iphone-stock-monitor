import requests
import time
import random
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

API_BASE = "https://www.apple.com/sg/shop/fulfillment-messages"
PRODUCT_PAGE = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro"  # 用这个或苹果主页获取 cookie

# 你要检测的两个 part numbers
PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A",
}

# 你可以先搞一个门店列表（store numbers），也可以每次从 pickup-message 接口获取所有店铺
# 这里先举例一个店铺 R633（Marina Bay Sands）做测试
STORE_LIST = ["R633"]  # 你可以把整个新加坡的店铺编号加进来

HEADERS_COMMON = {
    "Accept": "*/*",
    "Accept-Language": "en,zh-CN;q=0.9,zh;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}


def send_telegram(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram token / chat id 未配置")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        r = requests.post(url, data=data, timeout=10)
        print("Telegram status:", r.status_code, "| resp:", r.text)
    except Exception as e:
        print("Telegram 发送异常：", e)


def get_session_with_cookies():
    """访问产品页或首页获取 cookies"""
    session = requests.Session()
    headers = HEADERS_COMMON.copy()
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    # 随机延迟
    time.sleep(random.randint(2, 6))
    try:
        resp = session.get(PRODUCT_PAGE, headers=headers, timeout=10)
        resp.raise_for_status()
        print("主页访问成功，cookies 获取完成")
    except Exception as e:
        print("主页访问失败：", e)
    return session


def check_one_part(session, part_number, store):
    """检测一个 part 在某个 store 的库存"""
    params = {
        "fae": "true",
        "pl": "true",
        "mts.0": "regular",
        "mts.1": "compact",
        "parts.0": part_number,
        "searchNearby": "true",
        "store": store,
    }
    headers = HEADERS_COMMON.copy()
    headers["Referer"] = PRODUCT_PAGE
    try:
        r = session.get(API_BASE, params=params, headers=headers, timeout=10)
        print("请求 URL:", r.url)
        print("状态码:", r.status_code)
        r.raise_for_status()
        data = r.json()
        # 读取库存状态
        stores_info = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
        for st in stores_info:
            avail = st.get("partsAvailability", {}).get(part_number, {}).get("pickupDisplay")
            stname = st.get("storeName")
            print(f"  店铺 {stname}, part {part_number}: {avail}")
            return avail
    except Exception as e:
        print("检测异常：", e)
    return None


def main():
    session = get_session_with_cookies()
    for name, part in PARTS.items():
        print(f"检测型号 —— {name} ({part})")
        for store in STORE_LIST:
            status = check_one_part(session, part, store)
            if status and status.lower() == "available":
                send_telegram(f"✅ 有库存: {name} 在 店铺 {store}")
            # else 不通知，也可打印
        print()
    print("检查结束")


if __name__ == "__main__":
    print("🟢 开始检查库存…")
    main()
    print("🟢 结束")
