#!/usr/bin/env python3
"""
check_stock_curl.py

用 Selenium 自动获取 cookie -> 用 curl 发请求到 Apple fulfillment-messages 接口（curl 风格）
打印访问 URL / 状态码 / 部分响应，遇到 541 明确输出 URL 与响应片段
检测到库存时发送 Telegram 消息
"""

import subprocess
import os
import time
import json
import shlex
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# =========== 配置（可按需修改） ===========
# 从环境变量读取 Telegram 配置（在 GitHub Actions 中请用 Secrets）
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 要检测的机型：显示名 -> part number (SKU)
PARTS = {
    "Cosmic Orange 256GB": "MFYN4X/A",
    "Deep Blue 256GB": "MG8J4X/A"
}

# 新加坡三家 Apple Store 编号（你已确认）
STORES = ["R633", "R641", "R625"]

# 访问间隔（秒），避免请求太频繁
DELAY_BETWEEN_REQUESTS = 1.5

# curl 请求中常用 header（你可以按需扩展/替换）
CURL_HEADERS = [
    ("accept", "*/*"),
    ("accept-language", "en,zh-CN;q=0.9,zh;q=0.8"),
    # referer 可根据你想模拟的页面设置
    ("referer", "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"),
    # 以下 sec-ch-ua 等可选
    ("sec-ch-ua", '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"'),
    ("sec-ch-ua-mobile", "?0"),
    ("sec-ch-ua-platform", '"Windows"'),
    ("sec-fetch-dest", "empty"),
    ("sec-fetch-mode", "cors"),
    ("sec-fetch-site", "same-origin"),
    # user-agent 尽量用常见浏览器 UA
    ("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    # x-aos-ui-fetch-call-1：浏览器每次请求可能不同，但可留空或固定（若你有实测值可填）
    #("x-aos-ui-fetch-call-1", "32ak9h5ced-mg582ox5"),
]

# =========== 工具函数 ===========

def send_telegram(message: str):
    """发送 Telegram 消息（如果已配置 token & chat_id）"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram 未配置，跳过推送")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )
        if resp.status_code != 200:
            print("❌ Telegram 发送失败:", resp.status_code, resp.text)
    except Exception as e:
        print("❌ Telegram 异常:", e)


def build_cookie_header_from_selenium_cookies(selenium_cookies):
    """
    selenium_cookies: list of dicts from driver.get_cookies()
    returns: cookie string suitable for curl -b "k=v; k2=v2"
    """
    return "; ".join([f"{c['name']}={c['value']}" for c in selenium_cookies])


def get_latest_cookies_via_selenium(headless=True, wait_seconds=4):
    """
    使用 webdriver-manager + selenium 启动 Chrome（无头）访问苹果商品页并返回 cookie 字符串
    """
    chrome_options = Options()
    if headless:
        # 推荐使用 new headless mode
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # 可添加更多参数如 window-size 等
    chrome_options.add_argument("--window-size=1200,900")

    # 安装并使用 ChromeDriver（webdriver-manager 会自动下载匹配驱动）
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        # 打开一个真实存在的商品页以获取上下文 cookie（避免 404）
        product_page = "https://www.apple.com/sg/shop/buy-iphone/iphone-17-pro/6.9-inch-display-256gb-cosmic-orange"
        driver.get(product_page)
        # 给页面一点时间加载资源 / cookie 被设置
        time.sleep(wait_seconds)
        selenium_cookies = driver.get_cookies()
        cookie_str = build_cookie_header_from_selenium_cookies(selenium_cookies)
        print("✅ Selenium 获取 cookie 完成，cookie 字段长度:", len(cookie_str))
        return cookie_str
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def run_curl_and_capture(url: str, cookie_str: str, extra_headers=None, timeout=20):
    """
    使用 curl 发起请求并返回 (http_status:int, body:str)
    - 以 curl -sS -o - -w "%{http_code}" 把响应体 + 状态码一起返回
    - extra_headers: list of (name, value)
    """
    if extra_headers is None:
        extra_headers = []

    # 构建 curl 命令
    cmd = ["curl", "-sS", "-o", "-", "-w", "%{http_code}", url]
    # 添加 headers
    for (k, v) in CURL_HEADERS + extra_headers:
        # 避免空 header entries
        if v is None or v == "":
            continue
        # header format: -H "Key: Value"
        cmd.extend(["-H", f"{k}: {v}"])
    # 添加 cookie header（使用 -H "Cookie: ..." 而不是 -b 来保证格式）
    if cookie_str:
        cmd.extend(["-H", f"Cookie: {cookie_str}"])

    # 可选：增加 --max-time timeout
    cmd.extend(["--max-time", str(timeout)])

    # 调用 curl
    # print("DEBUG curl cmd:", " ".join(shlex.quote(p) for p in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout
    stderr = proc.stderr
    returncode = proc.returncode

    if returncode != 0:
        # curl 本身失败（超时、网络问题等）
        raise RuntimeError(f"curl exit {returncode}, stderr: {stderr.strip()}")

    # 最后三个字符是 HTTP 状态码（%{http_code} 的输出）
    if len(stdout) < 3:
        raise RuntimeError("curl output too short to contain http code")
    http_code = int(stdout[-3:])
    body = stdout[:-3]
    return http_code, body


# =========== 主逻辑 ===========

def parse_availability_from_response_body(body: str):
    """
    尝试从 body（通常是 JSON）解析出是否有库存和简短说明。
    Apple 的响应格式复杂，这里做保守解析：
      - 若能解析为 JSON，寻找 pickupMessage -> stores -> partsAvailability
      - 返回简短文本（最多 800 字）方便通知和日志
    """
    try:
        j = json.loads(body)
    except Exception:
        # 非 JSON 响应（可能是 HTML 错误页）
        snippet = body.strip().replace("\n", " ")[:800]
        return False, f"(非 JSON 响应) {snippet}"

    # 先尝试常见路径
    pickup = j.get("body", {}).get("content", {}).get("pickupMessage")
    if pickup:
        # 拼一段可读的描述（遍历 stores）
        stores = pickup.get("stores") if isinstance(pickup, dict) else None
        if stores:
            lines = []
            any_available = False
            for s in stores:
                store_name = s.get("storeName", s.get("retailStore", {}).get("name", "unknown"))
                part_info = s.get("partsAvailability", {})
                info_for_part = []
                for part_num, info in part_info.items():
                    display = info.get("pickupDisplay") or info.get("pickupSearchQuote") or str(info)
                    info_for_part.append(f"{part_num}: {display}")
                    # 判断是否可购买
                    is_buyable = info.get("buyability", {}).get("isBuyable")
                    if is_buyable:
                        any_available = True
                lines.append(f"{store_name} -> " + "; ".join(info_for_part))
            return any_available, "\n".join(lines)[:2000]
    # 尝试备用路径
    if isinstance(j.get("body"), dict):
        # sometimes stores put elsewhere
        stores = j.get("body").get("stores") or j.get("body").get("availability") or None
        if stores:
            snippet = json.dumps(stores)[:800]
            return False, snippet

    # fallback: return short JSON summary
    snippet = json.dumps(j)[:800]
    return False, snippet


def main():
    print("🟢 开始检查 - Selenium 获取 cookie -> curl 请求（curl 风格）")
    # 1. 获取最新 cookie 字符串
    try:
        cookie_str = get_latest_cookies_via_selenium()
    except Exception as e:
        print("❌ 使用 Selenium 获取 cookie 失败:", e)
        # 在失败时也尝试继续但没有 cookie（很可能被 541）
        cookie_str = ""

    all_messages = []
    for model_name, part_number in PARTS.items():
        for store in STORES:
            url = (
                "https://www.apple.com/sg/shop/fulfillment-messages?"
                f"fae=true&pl=true&mts.0=regular&mts.1=compact"
                f"&parts.0={part_number}&searchNearby=true&store={store}"
            )
            print("\n---")
            print("请求 URL:", url)
            try:
                http_code, body = run_curl_and_capture(url, cookie_str)
            except Exception as e:
                print("❌ curl 请求失败（本地错误）:", e)
                # 打印 URL 便于调试
                print("URL:", url)
                continue

            print("HTTP 状态码:", http_code)
            # 打印前 1000 字以便调试（不要太长）
            preview = body.replace("\n", " ")[:1000]
            print("响应片段:", preview)

            # 处理 541 或其他非 200 情况
            if http_code == 541:
                print(f"⚠️ 收到 541 Server Error（Apple 端拒绝）。URL: {url}")
                # 将响应片段加入日志，便于排查
                print("541 响应片段:", preview)
                # 不立刻重试（可按需实现重试逻辑）
                continue
            if http_code != 200:
                print(f"⚠️ 非 200 响应: {http_code}. URL: {url}")
                continue

            # 尝试解析 JSON 并判断是否有库存
            has_stock, summary = parse_availability_from_response_body(body)
            print("解析结果 has_stock:", has_stock)
            print("解析摘要:", summary)

            if has_stock:
                message = f"✅ 库存提醒：{model_name} 在 {store} 可能有货！\n{summary}\nURL: {url}"
                print("触发通知:", message)
                send_telegram(message)
                all_messages.append(message)

            # 避免请求太密集
            time.sleep(DELAY_BETWEEN_REQUESTS)

    if not all_messages:
        print("🟢 本次未检测到可用库存。")
    print("🟢 检查结束")
    # 脚本结束


if __name__ == "__main__":
    main()
