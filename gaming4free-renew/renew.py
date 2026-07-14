#!/usr/bin/env python3
"""
gaming4free 自动续期脚本 (Console +90 min 版)
- SeleniumBase UC 模式 + 代理
- 直接进入 Console 页面
- 自动点击 +90 min 按钮
- 自动循环续期到 48 小时
- TG 通知 (统一 emoji 格式)
"""

import os
import time
import urllib.request
import urllib.parse
from seleniumbase import SB

# ================== 环境变量 ==================
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_TOKEN   = os.environ.get("TG_BOT_TOKEN", "").strip()

raw_accounts = os.environ.get("GAME4FREE_ACCOUNT", "").strip().splitlines()
ACCOUNTS = []
for line in raw_accounts:
    line = line.strip()
    if not line:
        continue
    parts = line.split(",", 1)
    if len(parts) == 2:
        ACCOUNTS.append((parts[0].strip(), parts[1].strip()))

TARGET_SECONDS = 48 * 3600  # 48小时上限
ADD_SECONDS = 90 * 60       # 每次 +90 分钟
COOLDOWN_SEC = 300           # 冷却 5 分钟
MAX_ROUNDS = 10              # 最多 10 轮

# ================== 工具函数 ==================
def now_str():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print(f"{msg}", flush=True)

def send_tg(result, server_name="", expiry=""):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    msg = (
        f"🎮Game4Free 续期通知\n"
        f"⏰运行时间: {now_str()}\n"
        f"🖥️服务器: {server_name}\n"
    )
    if expiry:
        msg += f"🔢利用期限: {expiry}\n"
    msg += f"📊续期结果: {result}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            log("📨 TG推送成功")
    except Exception as e:
        log(f"⚠️ TG推送失败: {e}")

def parse_countdown_seconds(text):
    """解析 'HH:MM:SS' 或 'Xh Ym' 格式的时间"""
    if not text:
        return 0
    text = text.strip()
    # HH:MM:SS
    parts = text.split(":")
    if len(parts) == 3:
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except:
            pass
    # Xh Ym
    import re
    h = re.search(r'(\d+)\s*h', text, re.I)
    m = re.search(r'(\d+)\s*m', text, re.I)
    total = 0
    if h: total += int(h.group(1)) * 3600
    if m: total += int(m.group(1)) * 60
    return total

def format_hms(seconds):
    seconds = max(0, int(seconds))
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# ================== 续期逻辑 ==================
def get_remaining_time(sb):
    """从 console 页面读取剩余时间"""
    try:
        # 尝试多种选择器读取时间
        selectors = [
            '[class*="timer"]',
            '[class*="remaining"]',
            '[class*="countdown"]',
            '#sd-timer',
            '[class*="time-remaining"]',
            '[data-timer]',
        ]
        for sel in selectors:
            try:
                text = sb.execute_script(f"""
                    var el = document.querySelector('{sel}');
                    return el ? el.textContent.trim() : '';
                """)
                if text and len(text) < 30:
                    secs = parse_countdown_seconds(text)
                    if secs > 0:
                        return text, secs
            except:
                continue

        # 也尝试从页面文本提取时间
        page_text = sb.execute_script("return document.body ? document.body.innerText : '';")
        if page_text:
            import re
            # 找 HH:MM:SS 格式
            match = re.search(r'(\d{1,2}:\d{2}:\d{2})', page_text)
            if match:
                return match.group(1), parse_countdown_seconds(match.group(1))
            # 找 Xh Ym 格式
            match = re.search(r'(\d+h\s*\d*m)', page_text, re.I)
            if match:
                return match.group(1), parse_countdown_seconds(match.group(1))
    except:
        pass
    return "", 0

def click_plus_90(sb):
    """点击 +90 min 按钮"""
    selectors = [
        'button:has-text("+90")',
        'button:has-text("90 min")',
        'button:has-text("+ 90")',
        'button:has-text("90min")',
        'a:has-text("+90")',
        'a:has-text("90 min")',
        '[class*="extend"]',
        '[class*="renew"]',
        '[class*="add-time"]',
        '[class*="plus-90"]',
        '[id*="extend"]',
        '[id*="renew"]',
    ]

    for sel in selectors:
        try:
            count = sb.execute_script(f"return document.querySelectorAll('{sel}').length;")
            if count > 0:
                sb.execute_script(f"document.querySelector('{sel}')?.scrollIntoView({{block:'center'}})")
                time.sleep(0.5)
                # 用 JS 点击 (更可靠)
                sb.execute_script(f"document.querySelector('{sel}')?.click();")
                log(f"✅ 已点击 +90 min 按钮 (选择器: {sel})")
                return True
        except:
            continue

    return False

def handle_confirm(sb):
    """处理点击后可能出现的确认弹窗"""
    time.sleep(2)
    confirm_keywords = ['確認', '確定', 'OK', 'Confirm', '确认', 'Yes', 'はい', 'Continue']
    for kw in confirm_keywords:
        try:
            sel = f'button:has-text("{kw}")'
            count = sb.execute_script(f"return document.querySelectorAll('{sel}').length;")
            if count > 0:
                sb.execute_script(f"document.querySelector('{sel}')?.click();")
                log(f"✅ 已点击确认按钮: {kw}")
                time.sleep(2)
                return True
        except:
            continue

    # 也检查 native confirm() 弹窗
    try:
        sb.execute_script("""
            if (window.confirm) {
                var origConfirm = window.confirm;
                window.confirm = function() { return true; };
            }
        """)
    except:
        pass

    return False

def renew_account(sb, server_name, renew_url):
    """续期单台服务器"""
    log(f"\n🎮 开始续期: {server_name}")

    # 从 URL 提取 slug
    slug = renew_url.rstrip('/').split('/')[-1]

    # 打开 console 页面
    console_url = f"https://control.gaming4free.net/server/{slug}/console"
    log(f"🔗 打开 console 页面: {console_url}")
    sb.uc_open_with_reconnect(console_url, reconnect_time=6)
    time.sleep(5)

    # 读取当前剩余时间
    time_text, time_secs = get_remaining_time(sb)
    if time_text:
        log(f"📅 当前剩余: {time_text} ({time_secs // 3600}h {(time_secs % 3600) // 60}m)")
    else:
        log("⚠️ 未读取到剩余时间")

    # 检查是否已达上限
    if time_secs + ADD_SECONDS > TARGET_SECONDS:
        log(f"✅ 已达 48h 上限, 跳过")
        return time_text, time_secs, True  # 已达上限

    # 点击 +90 min 按钮
    log("🔍 查找 +90 min 按钮...")
    if not click_plus_90(sb):
        log("❌ 未找到 +90 min 按钮")
        # 打印所有按钮帮助诊断
        try:
            btns = sb.execute_script("""
                return Array.from(document.querySelectorAll('button, a[class*="btn"]'))
                    .map(b => b.innerText.trim())
                    .filter(t => t.length > 0 && t.length < 50);
            """)
            log(f"📋 页面所有按钮: {btns}")
        except:
            pass
        sb.save_screenshot(f"no_btn_{server_name}.png")
        return time_text, time_secs, False

    # 处理确认弹窗
    handle_confirm(sb)
    time.sleep(3)

    # 重新读取剩余时间
    new_text, new_secs = get_remaining_time(sb)
    if new_text:
        log(f"📅 续期后剩余: {new_text} ({new_secs // 3600}h {(new_secs % 3600) // 60}m)")

    # 判断是否成功
    if new_secs > time_secs:
        log(f"✅ 续期成功! {time_text} → {new_text}")
        return new_text, new_secs, True
    else:
        log(f"⚠️ 时间未变化, 可能需要等待冷却")
        return time_text, time_secs, False

# ================== 主流程 ==================
def run_script():
    if not ACCOUNTS:
        log("❌ 未解析到任何账号，请检查 GAME4FREE_ACCOUNT 格式")
        log("   格式: 服务器名,https://gaming4free.net/servers/xxx")
        exit(1)

    log(f"📋 共 {len(ACCOUNTS)} 个账号")

    # 代理配置
    IS_PROXY_ENV = os.environ.get("IS_PROXY", "false").lower() == "true"
    PROXY_SERVER_ENV = os.environ.get("PROXY_SERVER", "").strip()
    sb_kwargs = {"uc": True, "test": True}
    if IS_PROXY_ENV and PROXY_SERVER_ENV:
        sb_kwargs["proxy"] = PROXY_SERVER_ENV
        log(f"🔗 使用代理: {PROXY_SERVER_ENV}")
    else:
        log("🌐 直连模式")

    log("🔧 启动浏览器...")
    with SB(**sb_kwargs) as sb:
        log("🚀 浏览器就绪!")

        # 验证出口 IP
        try:
            sb.open("https://api.ipify.org/?format=json")
            ip = sb.get_text('body')[:50]
            log(f"📍 出口IP: {ip}")
        except:
            log("⚠️ IP验证超时")

        remaining = {}
        final_tg = {}

        for server_name, renew_url in ACCOUNTS:
            remaining[server_name] = 0
            final_tg[server_name] = {"expiry": "", "result": "❌续期失败"}

        round_num = 0
        while any(remaining[name] + ADD_SECONDS <= TARGET_SECONDS for name, _ in ACCOUNTS) and round_num < MAX_ROUNDS:
            round_num += 1
            log(f"\n{'='*50}")
            log(f"🔄 第 {round_num}/{MAX_ROUNDS} 轮续期")
            log(f"{'='*50}")

            for server_name, renew_url in ACCOUNTS:
                if remaining[server_name] + ADD_SECONDS > TARGET_SECONDS:
                    log(f"✅ [{server_name}] 已达 48h 上限, 跳过")
                    continue

                time_text, time_secs, success = renew_account(sb, server_name, renew_url)

                if success:
                    if time_secs > 0:
                        remaining[server_name] = time_secs
                    else:
                        remaining[server_name] += ADD_SECONDS
                    final_tg[server_name] = {
                        "expiry": time_text or format_hms(remaining[server_name]),
                        "result": "✅续期成功！"
                    }
                else:
                    # 失败了也记录当前时间
                    if time_secs > 0:
                        remaining[server_name] = time_secs

                # 冷却等待
                if not success and round_num < MAX_ROUNDS:
                    log(f"⏳ 等待 {COOLDOWN_SEC} 秒冷却...")
                    time.sleep(COOLDOWN_SEC)

            if any(remaining[name] + ADD_SECONDS <= TARGET_SECONDS for name, _ in ACCOUNTS) and round_num < MAX_ROUNDS:
                log(f"⏳ 等待 20 秒后继续...")
                time.sleep(20)

        # 最终状态
        all_success = all(remaining[name] + ADD_SECONDS > TARGET_SECONDS for name, _ in ACCOUNTS)
        if all_success:
            log("\n🎉 所有服务器均已达到 48h 上限!")
        else:
            log("\n❌ 达到最大重试次数, 部分服务器未续期成功")
            for name, _ in ACCOUNTS:
                secs = remaining[name]
                if secs + ADD_SECONDS <= TARGET_SECONDS:
                    log(f"   ❌ {name}: 未续期成功 (剩余 {secs//3600}h {(secs%3600)//60}m)")

    # TG 通知
    log("\n📋 推送 TG 通知...")
    for server_name, _ in ACCOUNTS:
        info = final_tg.get(server_name, {"expiry": "", "result": "❌无记录"})
        send_tg(info["result"], server_name, info["expiry"])

if __name__ == "__main__":
    run_script()
