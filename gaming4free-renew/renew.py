#!/usr/bin/env python3
"""
gaming4free 自动续期脚本 (sing-box 代理版)
- sing-box SOCKS5 代理 (socks5://127.0.0.1:1080)
- SeleniumBase UC mode + Turnstile 验证
- 投票 API 续期, 每次 +90 分钟, 上限 48 小时
- TG 通知 (统一 emoji 格式)
"""

import os
import re
import time
import json
import random
import string
import subprocess
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

# sing-box 代理地址 (setup_proxy.sh 启动后自动监听)
LOCAL_PROXY = "socks5://127.0.0.1:1080"
IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"

TARGET_SECONDS = 48 * 3600  # 48小时上限

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
    try:
        parts = text.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except:
        pass
    return 0

def format_hms(seconds):
    seconds = max(0, int(seconds))
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# ================== 随机用户名 ==================
MC_PREFIXES = ["Steve", "Alex", "Notch", "Creeper", "Enderman", "Dragon", "Wither",
               "Shadow", "Dark", "Night", "Pro", "Epic", "Ultra", "Super", "Mega"]
MC_SUFFIXES = ["PVP", "Gaming", "HD", "YT", "MC", "XD", "GG", "OP", "Craft", "Mine"]

def random_mc_username():
    style = random.randint(1, 4)
    if style == 1:
        name = random.choice(MC_PREFIXES) + str(random.randint(10, 9999))
    elif style == 2:
        name = random.choice(MC_PREFIXES) + random.choice(MC_SUFFIXES)
    elif style == 3:
        name = random.choice(MC_PREFIXES) + "_" + random.choice(MC_PREFIXES)
    else:
        name = random.choice(string.ascii_uppercase) + ''.join(
            random.choices(string.ascii_letters + string.digits, k=random.randint(7, 11)))
    return name[:16]

# ================== Turnstile 处理 ==================
EXPAND_POPUP_JS = """
(function() {
    var t = document.querySelector('input[name="cf-turnstile-response"]');
    if (!t) return;
    var el = t;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden') el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
})();
"""

INJECT_TOKEN_LISTENER_JS = """
(function() {
    if (window.__cf_token_listener__) return;
    window.__cf_token_listener__ = true;
    window.__cf_turnstile_token__ = '';
    window.addEventListener('message', function(e) {
        try {
            var d = e.data;
            if (!d || d.event === 'food') return;
            var token = d.token || d.response;
            if (token && token.length > 20) {
                window.__cf_turnstile_token__ = token;
                var inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
                inputs.forEach(function(input) {
                    var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    nativeSet.call(input, token);
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                });
            }
        } catch(err) {}
    });
})();
"""

GET_COORDS_JS = """
(function() {
    var a = document.querySelector('input[name="cf-turnstile-response"]');
    if (!a) return {error: 'no_anchor'};
    a = a.parentElement;
    if (!a) return {error: 'no_anchor'};
    var r = a.getBoundingClientRect();
    if (r.width === 0) return {error: 'zero_size'};
    return {
        vx: Math.round(r.left + r.width/2 - 130),
        vy: Math.round(r.top + r.height/2),
        wx: window.screenX || 0,
        wy: window.screenY || 0,
        oh: window.outerHeight, ih: window.innerHeight,
        ow: window.outerWidth, iw: window.innerWidth
    };
})()
"""

def xdotool_click(x, y, label=""):
    try:
        subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"],
                       check=True, capture_output=True)
        if label: log(label)
        return True
    except:
        return False

def get_turnstile_token(sb):
    try:
        return sb.execute_script("""
            var t = window.__cf_turnstile_token__ || '';
            if (t && t.length > 20) return t;
            var i = document.querySelector('input[name="cf-turnstile-response"]');
            return (i && i.value && i.value.length > 20) ? i.value : '';
        """) or ''
    except:
        return ''

def turnstile_exists(sb):
    try:
        return sb.execute_script(
            'return document.querySelector(\'input[name="cf-turnstile-response"]\') !== null;')
    except:
        return False

def solve_turnstile(sb):
    for _ in range(3):
        sb.execute_script(EXPAND_POPUP_JS)
        time.sleep(0.5)

    if get_turnstile_token(sb):
        log("✅ 验证已自动通过")
        return True

    time.sleep(1.5)
    result = sb.execute_script(GET_COORDS_JS)
    if not result or result.get('error'):
        # 无感盾, 等 token
        for _ in range(60):
            if get_turnstile_token(sb):
                log("✅ 无感盾 token 已获取")
                return True
            time.sleep(0.5)
        log("❌ 无感盾 token 等待超时")
        return False

    vp_x = result['vx']; vp_y = result['vy']
    win_x = result['wx']; win_y = result['wy']
    toolbar_h = result['oh'] - result['ih']
    border_l = (result['ow'] - result['iw']) / 2 if result['ow'] > result['iw'] else 0
    abs_x = int(vp_x + win_x + border_l)
    abs_y = int(vp_y + win_y + toolbar_h)

    for click_num in range(3):
        if click_num > 0: time.sleep(3)
        xdotool_click(abs_x, abs_y, f"📐 坐标点击 {click_num+1}")
        for _ in range(150):
            if get_turnstile_token(sb):
                log("✅ Turnstile 验证通过!")
                return True
            time.sleep(0.1)

    log("❌ 人机验证超时")
    return False

# ================== 投票 API ==================
def extract_slug(url):
    return url.rstrip('/').split('/')[-1]

def submit_vote(sb, slug, token, username):
    body = json.dumps({
        "cf-turnstile-response": token,
        "voter_name": username,
        "ad_watched": "0"
    })
    sb.execute_script(f"""
        window.__vote_result__ = null;
        (async function() {{
            try {{
                var r = await fetch('https://control.gaming4free.net/api/servers/{slug}/vote', {{
                    method: 'POST', mode: 'cors', credentials: 'omit',
                    headers: {{'Content-Type': 'application/json', 'Accept': 'application/json'}},
                    body: {body!r}
                }});
                window.__vote_result__ = {{status: r.status, data: await r.json()}};
            }} catch(e) {{
                window.__vote_result__ = {{status: 0, data: {{success: false, message: e.toString()}}}};
            }}
        }})();
    """)

def clear_cache(sb):
    try:
        sb.delete_all_cookies()
        sb.execute_script("try{sessionStorage.clear();}catch(e){} try{localStorage.clear();}catch(e){}")
    except:
        pass

# ================== 续期单台服务器 ==================
def renew_account(sb, server_name, renew_url):
    log(f"\n🎮 开始续期: {server_name}")
    username = random_mc_username()
    slug = extract_slug(renew_url)

    log("🔗 打开续期页面...")
    sb.uc_open_with_reconnect(renew_url, reconnect_time=4)
    time.sleep(3)

    log("🔍 查找 VOTE 按钮...")
    vote_clicked = False
    vote_selectors = [
        '#sd-vote-btn',
        'button:has-text("VOTE")',
        'button:has-text("Vote")',
        'button:has-text("vote")',
        'a:has-text("VOTE")',
        'a:has-text("Vote")',
        '[class*="vote"]',
        '[id*="vote"]',
    ]
    for sel in vote_selectors:
        try:
            sb.wait_for_element_visible(sel, timeout=5)
            sb.execute_script(f"document.querySelector('{sel}')?.scrollIntoView({{block:'center'}})")
            time.sleep(0.3)
            sb.click(sel)
            log(f"✅ 已点击 VOTE 按钮 (选择器: {sel})")
            vote_clicked = True
            break
        except:
            continue

    if not vote_clicked:
        log("❌ VOTE 按钮未找到")
        # 打印页面所有按钮文字, 帮助诊断
        try:
            btns = sb.execute_script("""
                return Array.from(document.querySelectorAll('button, a')).map(b => b.innerText.trim()).filter(t => t.length > 0 && t.length < 50);
            """)
            log(f"📋 页面所有按钮: {btns}")
        except:
            pass
        clear_cache(sb)
        return ''

    time.sleep(1)

    # 等待 Turnstile
    for attempt in range(3):
        for _ in range(20):
            if turnstile_exists(sb):
                break
            time.sleep(0.5)
        if turnstile_exists(sb):
            break
        try:
            sb.click('#sd-vote-btn')
        except:
            pass
        time.sleep(1)

    if not turnstile_exists(sb):
        log("❌ 验证组件未出现")
        return ''

    sb.execute_script(INJECT_TOKEN_LISTENER_JS)

    if not solve_turnstile(sb):
        clear_cache(sb)
        return ''

    token = get_turnstile_token(sb)
    if not token:
        log("❌ 未获取到 Token")
        clear_cache(sb)
        return ''

    log(f"👤 用户名: {username}")
    log("📤 提交投票...")
    submit_vote(sb, slug, token, username)

    # 等待 API 响应
    for _ in range(40):
        try:
            outcome = sb.execute_script("return window.__vote_result__;")
            if outcome:
                break
        except:
            pass
        time.sleep(0.5)

    if not outcome:
        log("❌ API 无响应")
        clear_cache(sb)
        return ''

    data = outcome.get('data', {})
    if not data.get('success'):
        log(f"❌ 续期失败: {data.get('message', '未知')} (HTTP {outcome.get('status')})")
        clear_cache(sb)
        return ''

    try:
        secs = int(round(float(data.get('hours_remaining', 0)) * 3600))
    except:
        secs = 0
    expiry = format_hms(secs)

    log(f"✅ 续期成功: {data.get('message', '')}")
    log(f"📅 利用期限: {expiry}")
    clear_cache(sb)
    return expiry

# ================== 主流程 ==================
def run_script():
    if not ACCOUNTS:
        log("❌ 未解析到任何账号，请检查 GAME4FREE_ACCOUNT 格式")
        log(f"   格式: 服务器名,https://control.gaming4free.net/server/xxx/console")
        exit(1)

    log(f"📋 共 {len(ACCOUNTS)} 个账号")

    proxy_str = LOCAL_PROXY if IS_PROXY else None
    sb_kwargs = {"uc": True, "test": True}
    if proxy_str:
        sb_kwargs["proxy"] = proxy_str
        log(f"🔗 使用代理: {proxy_str}")
    else:
        log("🌐 直连模式 (无代理)")

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

        remaining = {name: 0 for name, _ in ACCOUNTS}
        final_tg = {}

        round_num = 0
        while any(remaining[name] + 90 * 60 <= TARGET_SECONDS for name, _ in ACCOUNTS):
            round_num += 1
            log(f"\n{'='*50}")
            log(f"🔄 第 {round_num} 轮续期")
            log(f"{'='*50}")

            for server_name, renew_url in ACCOUNTS:
                if remaining[server_name] + 90 * 60 > TARGET_SECONDS:
                    log(f"✅ [{server_name}] 已达48小时上限，跳过")
                    continue

                expiry = renew_account(sb, server_name, renew_url)
                if expiry:
                    new_secs = parse_countdown_seconds(expiry)
                    if new_secs > 0:
                        remaining[server_name] = new_secs
                    else:
                        remaining[server_name] += 90 * 60
                    final_tg[server_name] = {"expiry": expiry, "result": "✅续期成功！"}
                else:
                    if server_name not in final_tg:
                        final_tg[server_name] = {"expiry": "", "result": "❌续期失败"}

                time.sleep(2)

            if any(remaining[name] + 90 * 60 <= TARGET_SECONDS for name, _ in ACCOUNTS):
                log("⏳ 等待 20 秒后继续...")
                time.sleep(20)

        log("\n🎉 所有服务器均已达到48小时上限!")

    # TG 通知
    log("\n📋 推送 TG 通知...")
    for server_name, _ in ACCOUNTS:
        info = final_tg.get(server_name, {"expiry": "", "result": "❌无记录"})
        send_tg(info["result"], server_name, info["expiry"])

if __name__ == "__main__":
    run_script()
