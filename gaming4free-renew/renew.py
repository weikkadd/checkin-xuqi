#!/usr/bin/env python3
"""
gaming4free 自动续期脚本 (修正版)
- 增强了 +90 min 按钮的定位逻辑
- 增加了 JS 强制点击
- 增加了自动关闭广告/会员弹窗逻辑
"""

import os
import time
import urllib.request
import urllib.parse
from seleniumbase import SB

# ================== 环境变量 ==================
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_TOKEN   = os.environ.get("TG_BOT_TOKEN", "").strip()
GF_COOKIE  = os.environ.get("GAME4FREE_COOKIE", "").strip()

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
    if not text:
        return 0
    text = text.strip()
    parts = text.split(":")
    if len(parts) == 3:
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except:
            pass
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
    try:
        selectors = [
            '[class*="timer"]', '[class*="remaining"]', '[class*="countdown"]',
            '#sd-timer', '[class*="time-remaining"]', '[data-timer]',
        ]
        for sel in selectors:
            try:
                text = sb.execute_script(f"var el = document.querySelector('{sel}'); return el ? el.textContent.trim() : '';")
                if text and len(text) < 30:
                    secs = parse_countdown_seconds(text)
                    if secs > 0: return text, secs
            except: continue
        page_text = sb.execute_script("return document.body ? document.body.innerText : '';")
        if page_text:
            import re
            match = re.search(r'(\d{1,2}:\d{2}:\d{2})', page_text)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
            match = re.search(r'(\d+h\s*\d*m)', page_text, re.I)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
    except: pass
    return "", 0

def close_modals(sb):
    """尝试关闭可能遮挡按鈕的弹窗"""
    try:
        # 仅针对明显的弹窗关闭按钮
        close_selectors = [
            'button:contains("Maybe later")', 
            'button:contains("×")',
            '.modal-close',
            'button:contains("Enjoy ad-free")',
            '[aria-label="Close"]'
        ]
        for sel in close_selectors:
            try:
                # 检查元素是否存在且在 modal 或 dialog 中
                is_modal = sb.execute_script(f"""
                    var el = document.querySelector('{sel}');
                    if (!el) return false;
                    var p = el.parentElement;
                    while(p) {{
                        if (p.className.includes('modal') || p.className.includes('dialog') || p.tagName === 'DIALOG') return true;
                        p = p.parentElement;
                    }}
                    return false;
                """)
                if is_modal:
                    sb.click(sel)
                    log(f"🛡️ 已成功关闭弹窗: {sel}")
                    time.sleep(1)
            except: continue
    except: pass

def click_plus_90(sb):
    """增强版点击逻辑"""
    close_modals(sb)
    
    # 策略 1: 使用更真实的 JS 模拟点击事件
    js_click_script = """
    (function() {
        var targets = ["+ 90 min", "+90 min", "90 min"];
        var elements = document.querySelectorAll('button, a, span, strong, div');
        function simulateClick(el) {
            var evt1 = new MouseEvent("mousedown", {bubbles: true, cancelable: true, view: window});
            var evt2 = new MouseEvent("mouseup", {bubbles: true, cancelable: true, view: window});
            var evt3 = new MouseEvent("click", {bubbles: true, cancelable: true, view: window});
            el.dispatchEvent(evt1);
            el.dispatchEvent(evt2);
            el.dispatchEvent(evt3);
        }
        for (var el of elements) {
            var text = (el.innerText || "").trim();
            for (var t of targets) {
                if (text.includes(t) && text.length < 20) {
                    el.scrollIntoView({block: 'center', behavior: 'smooth'});
                    console.log("Target found:", text, el.tagName);
                    simulateClick(el);
                    // 如果是 span/strong，也尝试点击父级
                    if (el.tagName === 'SPAN' || el.tagName === 'STRONG') {
                        setTimeout(() => simulateClick(el.parentElement), 100);
                    }
                    return true;
                }
            }
        }
        return false;
    })();
    """
    try:
        success = sb.execute_script(js_click_script)
        if success:
            log("🚀 已通过 JS 脚本强制点击 +90 min 按钮")
            return True
    except Exception as e:
        log(f"⚠️ JS 点击异常: {e}")

    # 策略 2: XPath 定位
    xpaths = [
        "//*[contains(text(), '+ 90 min')]",
        "//*[contains(text(), '+90 min')]",
        "//button[contains(., '90')]",
        "//span[contains(., '90')]/.."
    ]
    for xpath in xpaths:
        try:
            if sb.is_element_visible(xpath):
                sb.click(xpath)
                log(f"✅ 已通过 XPath 成功点击: {xpath}")
                return True
        except: continue

    log("❌ 所有点击策略均告失败")
    return False

def handle_confirm(sb):
    """处理续期后的确认和 Cloudflare 验证"""
    time.sleep(3)
    
    # 1. 尝试处理 Cloudflare Turnstile 验证码
    try:
        # 循环检测验证码，增加初始等待
        for _ in range(8):
            cf_iframes = sb.find_elements('iframe[src*="cloudflare"]')
            if not cf_iframes:
                # 如果没看到验证码，多等 2 秒再看一次（可能弹窗有延迟）
                time.sleep(2)
                continue
            
            log(f"🛡️ 检测到 Cloudflare 验证码 (第 {_ + 1} 次尝试)...")
            # 尝试通过 UC 模式内置方法
            sb.uc_gui_click_captcha()
            
            # 检查是否还在“正在验证”状态
            is_verifying = sb.execute_script("""
                var iframes = document.querySelectorAll('iframe[src*="cloudflare"]');
                for (var f of iframes) {
                    try {
                        var doc = f.contentDocument || f.contentWindow.document;
                        if (doc.body.innerText.includes('正在验证') || doc.body.innerText.includes('Verifying')) return true;
                    } catch(e) {}
                }
                return false;
            """)
            if is_verifying:
                log("⏳ 验证码正在验证中，等待 5 秒...")
                time.sleep(5)
            else:
                log("✅ 验证码可能已通过或正在加载")
                time.sleep(3)
                break
    except Exception as e:
        log(f"⚠️ 验证码处理异常: {e}")

    # 2. 处理常规确认按钮
    confirm_keywords = ['確認', '確定', 'OK', 'Confirm', '确认', 'Yes', 'Continue', 'Verify']
    for kw in confirm_keywords:
        try:
            sb.execute_script(f"""
                var btns = document.querySelectorAll('button, a');
                for (var b of btns) {{
                    if (b.innerText.includes('{kw}')) {{
                        b.click();
                        return true;
                    }}
                }}
            """)
        except: continue
    return False

def renew_account(sb, server_name, renew_url):
    log(f"\n🎮 开始续期: {server_name}")
    parts = renew_url.rstrip('/').split('/')
    # 排除 'console', 'settings' 等关键字，找到真正的 slug
    slug = None
    for part in reversed(parts):
        if part and part.lower() not in ['console', 'settings', 'server', 'servers', 'vote']:
            # 典型的 slug 是字母数字组合，长度通常 >= 4
            if len(part) >= 4:
                slug = part
                break
    if not slug:
        slug = parts[-1] if parts else ''
    console_url = f"https://control.gaming4free.net/server/{slug}/console"
    log(f"🔗 打开 console 頁面: {console_url}")
    
    # 增加超时时间以适应慢速代理
    sb.uc_open_with_reconnect(console_url, reconnect_time=20)
    time.sleep(8)

    time_text, time_secs = get_remaining_time(sb)
    if time_text:
        log(f"📅 当前剩余: {time_text} ({time_secs // 3600}h {(time_secs % 3600) // 60}m)")
    
    if time_secs + ADD_SECONDS > TARGET_SECONDS:
        log(f"✅ 已达 48h 上限, 跳過")
        return time_text, time_secs, True

    log("🔍 查找 +90 min 按钮...")
    if not click_plus_90(sb):
        sb.save_screenshot(f"fail_{server_name}.png")
        return time_text, time_secs, False

    handle_confirm(sb)
    time.sleep(5) 
    
    # 续期成功后页面可能会跳转或刷新，重新打开 console 页面确保能读到时间
    sb.uc_open_with_reconnect(console_url, reconnect_time=15)
    time.sleep(5)

    new_text, new_secs = get_remaining_time(sb)
    if new_secs > time_secs:
        log(f"✅ 续期成功! {time_text} → {new_text}")
        return new_text, new_secs, True
    else:
        log(f"⚠️ 时间未变化，可能是按钮点击了但未触发、处于冷却期或验证未通过")
        # 诊断：查看页面是否还残留验证码
        if sb.find_elements('iframe[src*="cloudflare"]'):
            log("🛑 诊断：页面上仍存在验证码弹窗，验证可能未成功通过")
        return time_text, time_secs, False

def run_script():
    if not ACCOUNTS:
        log("❌ 未解析到任何账号")
        exit(1)

    sb_kwargs = {"uc": True, "test": True}
    if os.environ.get("IS_PROXY", "false").lower() == "true":
        # 优先读取 PROXY_URL，其次是 PROXY_SERVER
        proxy = os.environ.get("PROXY_URL") or os.environ.get("PROXY_SERVER")
        if proxy:
            sb_kwargs["proxy"] = proxy.strip()
            log(f"🔗 使用代理: {sb_kwargs['proxy']}")

    with SB(**sb_kwargs) as sb:
        if GF_COOKIE:
            sb.open("https://control.gaming4free.net/")
            time.sleep(2)
            sb.execute_script(f"""
                var cookieStr = {GF_COOKIE!r};
                cookieStr.split(';').forEach(function(c) {{
                    var parts = c.trim().split('=');
                    if (parts.length >= 2) {{
                        document.cookie = parts[0].trim() + '=' + parts.slice(1).join('=') + '; path=/; domain=.gaming4free.net';
                    }}
                }});
            """)
            sb.open("https://control.gaming4free.net/") # 刷新以应用 Cookie
            time.sleep(2)

        for server_name, renew_url in ACCOUNTS:
            success_count = 0
            for r in range(MAX_ROUNDS):
                log(f"\n🔄 [{server_name}] 第 {r+1}/{MAX_ROUNDS} 轮尝试")
                try:
                    time_text, time_secs, success = renew_account(sb, server_name, renew_url)
                except Exception as e:
                    log(f"❌ 第 {r+1} 轮异常: {e}")
                    time_text, time_secs, success = "", 0, False

                if success:
                    if time_secs + ADD_SECONDS > TARGET_SECONDS:
                        send_tg("✅ 已达48h上限", server_name, time_text)
                        break
                    send_tg("✅续期成功", server_name, time_text)
                    success_count += 1
                else:
                    log(f"⚠️ 第 {r+1} 轮未成功, 继续重试")

                if r < MAX_ROUNDS - 1:
                    log(f"⏳ 等待 {COOLDOWN_SEC} 秒冷却...")
                    time.sleep(COOLDOWN_SEC)

if __name__ == "__main__":
    run_script()
