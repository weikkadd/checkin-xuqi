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

GOST_PROCESS = None
PROXIES = []  # list of (name, proxy_url)

def load_proxies():
    global PROXIES
    raw = os.environ.get("GAME4FREE_PROXY", "").strip()
    PROXIES = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 1)
        if len(parts) == 2:
            PROXIES.append((parts[0].strip(), parts[1].strip()))
        else:
            log(f"⚠️ 代理格式错误，跳过：{line}")
    if len(PROXIES) < 2:
        log(f"⚠️ 仅检测到 {len(PROXIES)} 条代理，建议配置 2 条交替使用")

def start_gost(proxy_name: str, proxy_url: str):
    global GOST_PROCESS
    stop_gost()
    log(f"🛡️ 启动 GOST 代理：{proxy_name}")
    try:
        GOST_PROCESS = subprocess.Popen(
            ["./gost", "-L", "http://:8080", "-F", proxy_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        log("✅ GOST 已启动")
    except Exception as e:
        log(f"❌ GOST 启动失败：{e}")

def stop_gost():
    global GOST_PROCESS
    if GOST_PROCESS and GOST_PROCESS.poll() is None:
        GOST_PROCESS.terminate()
        try:
            GOST_PROCESS.wait(timeout=5)
        except Exception:
            GOST_PROCESS.kill()
        GOST_PROCESS = None
        log("🛑 GOST 已停止")
        log("=" * 50)

LOCAL_PROXY = "http://127.0.0.1:8080"

_tg = os.environ["TG_BOT"].split(",")
TG_CHAT_ID = _tg[0].strip()
TG_TOKEN   = _tg[1].strip()

raw_accounts = os.environ["GAME4FREE_ACCOUNT"].strip().splitlines()
ACCOUNTS = []
for line in raw_accounts:
    line = line.strip()
    if not line:
        continue
    parts = line.split(",", 1)
    if len(parts) == 2:
        ACCOUNTS.append((parts[0].strip(), parts[1].strip()))


def now_str():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print(f"{msg}", flush=True)


MC_PREFIXES = [
    "Steve", "Alex", "Notch", "Herobrine", "Creeper",
    "Enderman", "Skeleton", "Zombie", "Spider", "Ghast",
    "Dragon", "Wither", "Blaze", "Slime", "Golem",
    "Shadow", "Dark", "Night", "Void", "Storm",
    "Fire", "Ice", "Thunder", "Frost", "Nether",
    "Pro", "Epic", "Ultra", "Super", "Mega",
]

MC_SUFFIXES = [
    "PVP", "Gaming", "HD", "YT", "MC",
    "XD", "LOL", "GG", "OP", "FTW",
    "Craft", "Mine", "Build", "Play", "Run",
    "_420", "_69", "_123", "_007", "_999",
]

def random_mc_username() -> str:
    style = random.randint(1, 4)
    if style == 1:
        name = random.choice(MC_PREFIXES) + str(random.randint(10, 9999))
    elif style == 2:
        name = random.choice(MC_PREFIXES) + random.choice(MC_SUFFIXES)
    elif style == 3:
        name = random.choice(MC_PREFIXES) + "_" + random.choice(MC_PREFIXES)
    else:
        length = random.randint(8, 12)
        chars = string.ascii_letters + string.digits
        name = random.choice(string.ascii_uppercase) + ''.join(random.choices(chars, k=length - 1))
    name = name[:16]
    if len(name) < 3:
        name = name + str(random.randint(100, 999))
    return name


def send_tg(result, server_name="", expiry="", silent=False):
    msg = (
        f"🎮Game4Free 续期通知\n"
        f"⏰运行时间: {now_str()}\n"
        f"🖥️服务器: {server_name}\n"
    )
    if expiry:
        msg += f"🔢利用期限: {expiry}\n"
    msg += f"📊续期结果: {result}"
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            if not silent:
                log("📨 TG推送成功")
    except Exception as e:
        log(f"⚠️ TG推送失败：{e}")


def parse_countdown_seconds(text: str) -> int:
    try:
        text = text.strip()
        parts = text.split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
    except Exception:
        pass
    return 0


def format_hms(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def extract_expiry(sb) -> str:
    try:
        countdown = sb.execute_script(
            "return document.querySelector('#sd-timer')?.textContent.trim() || ''"
        ) or ''
        return countdown
    except Exception:
        return ''


EXPAND_POPUP_JS = """
(function() {
    var turnstileInput = document.querySelector('input[name="cf-turnstile-response"]');
    if (!turnstileInput) return;
    var el = turnstileInput;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var style = window.getComputedStyle(el);
        if (style.overflow === 'hidden' || style.overflowX === 'hidden' || style.overflowY === 'hidden') {
            el.style.overflow = 'visible';
        }
        el.style.minWidth = 'max-content';
    }
})();
"""

INJECT_TOKEN_LISTENER_JS = """
(function() {
    if (window.__cf_token_listener_injected__) return;
    window.__cf_token_listener_injected__ = true;
    window.__cf_turnstile_token__ = '';

    window.addEventListener('message', function(e) {
        try {
            var d = e.data;
            if (!d || typeof d !== 'object') return;
            if (d.event === 'food') return;
            var token = d.token || d.response;
            if (token && token.length > 20) {
                window.__cf_turnstile_token__ = token;
                
                try { sessionStorage.setItem('__cf_turnstile_token__', token); } catch(err) {}

                var inputs = document.querySelectorAll(
                    'input[name="cf-turnstile-response"], input[name="cf_turnstile_response"]'
                );
                for (var i = 0; i < inputs.length; i++) {
                    try {
                        var nativeSet = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeSet.call(inputs[i], token);
                        inputs[i].dispatchEvent(new Event('input',  {bubbles: true}));
                        inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                    } catch(err) {
                        inputs[i].value = token;
                    }
                }
            }
        } catch(err) {}
    });
})();
"""

GET_COORDS_AND_INJECT_DOT_JS = """
(function() {
    var anchor = document.querySelector('input[name="cf-turnstile-response"]');
    if (!anchor) return { error: 'no_anchor' };
    anchor = anchor.parentElement;
    if (!anchor) return { error: 'no_anchor' };

    var rect = anchor.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return { error: 'zero_size' };

    var viewportX = rect.left + (rect.width / 2) - 130;
    var viewportY = rect.top + (rect.height / 2);

    var dot = document.getElementById('sniper-dot') || document.createElement('div');
    dot.id = 'sniper-dot';
    dot.style.position = 'fixed';
    dot.style.left = (viewportX - 5) + 'px';
    dot.style.top = (viewportY - 5) + 'px';
    dot.style.width = '10px';
    dot.style.height = '10px';
    dot.style.backgroundColor = 'red';
    dot.style.borderRadius = '50%';
    dot.style.zIndex = '99999999';
    dot.style.pointerEvents = 'none';
    dot.style.boxShadow = '0 0 5px rgba(255,0,0,0.8)';
    if (!document.getElementById('sniper-dot')) document.body.appendChild(dot);

    return {
        viewport_x: Math.round(viewportX),
        viewport_y: Math.round(viewportY),
        win_x:    window.screenX || 0,
        win_y:    window.screenY || 0,
        outer_h:  window.outerHeight,
        inner_h:  window.innerHeight,
        outer_w:  window.outerWidth,
        inner_w:  window.innerWidth
    };
})()
"""

def xdotool_click(x, y, label="📐 坐标点击成功"):
    x, y = int(x), int(y)
    try:
        subprocess.run(
            ["xdotool", "mousemove", str(x), str(y), "click", "1"],
            check=True, capture_output=True
        )
        log(label)
        return True
    except subprocess.CalledProcessError as e:
        log(f"⚠️ xdotool执行异常: {e.stderr.decode().strip()}")
        return False
    except Exception as e:
        log(f"⚠️ xdotool执行异常: {e}")
        return False


def get_turnstile_metrics(sb):
    for _ in range(10):
        result = sb.execute_script(GET_COORDS_AND_INJECT_DOT_JS)
        if result is None or result.get('error') == 'no_anchor':
            log("⚠️ 未找到锚点元素，等待重试...")
            time.sleep(1)
            continue
        if result.get('error') == 'zero_size':
            log("⚠️ 这是一个 0x0 无感盾，等待 token 自动出现...")
            deadline = time.time() + 30
            while time.time() < deadline:
                token = get_turnstile_token(sb)
                if token:
                    log(f"✅ 无感盾 token 已自动获取：{token[:50]}...")
                    return {'zero_size': True}
                time.sleep(0.5)
            log("❌ 无感盾 token 等待超时")
            return None
        return result
    log("❌ 验证坐标获取失败（超时）")
    return None


def get_turnstile_token(sb) -> str:
    try:
        token = sb.execute_script("""
            (function(){
                var token = window.__cf_turnstile_token__ || window.sessionStorage?.getItem('__cf_turnstile_token__');
                if (token && token.length > 20) return token;
                var input = document.querySelector('input[name="cf-turnstile-response"]');
                return (input && input.value && input.value.length > 20) ? input.value : '';
            })()
        """)
        return token if token else ''
    except Exception:
        return ''


def turnstile_exists(sb) -> bool:
    try:
        return sb.execute_script(
            "(function(){ return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null; })()"
        )
    except Exception:
        return False


def inject_token_listener(sb):
    try:
        sb.execute_script(INJECT_TOKEN_LISTENER_JS)
        log("📡 开始监控Cloudflare Turnstile Token...")
    except Exception as e:
        log(f"⚠️ 监听器注入失败：{e}")


def solve_turnstile(sb) -> bool:
    for _ in range(3):
        sb.execute_script(EXPAND_POPUP_JS)
        time.sleep(0.5)

    if get_turnstile_token(sb):
        log("✅ 验证已自动通过")
        return True

    time.sleep(1.5)

    metrics = get_turnstile_metrics(sb)
    if metrics is None:
        sb.save_screenshot("turnstile_no_coords.png")
        return False

    # 无感盾已在 get_turnstile_metrics 里等到 token，直接返回成功
    if metrics.get('zero_size'):
        return True

    vp_x        = metrics['viewport_x']
    vp_y        = metrics['viewport_y']
    win_x       = metrics['win_x']
    win_y       = metrics['win_y']
    toolbar_h   = metrics['outer_h'] - metrics['inner_h']
    border_left = (metrics['outer_w'] - metrics['inner_w']) / 2 \
                  if metrics['outer_w'] > metrics['inner_w'] else 0
    abs_x = int(vp_x + win_x + border_left)
    abs_y = int(vp_y + win_y + toolbar_h)
    log("📐 坐标计算完成")

    sb.save_screenshot("turnstile_click_pos.png")

    # 3连点，每次间隔3秒，点击后立即检测token
    click_labels = ["📐 坐标点击成功", "📐 坐标二击成功", "📐 坐标三击成功"]
    for click_num in range(1, 4):
        if click_num > 1:
            time.sleep(3)
        xdotool_click(abs_x, abs_y, click_labels[click_num - 1])
        deadline = time.time() + 15
        while time.time() < deadline:
            token = get_turnstile_token(sb)
            if token:
                log(f"✅ Cloudflare Turnstile 验证通过！token：{token[:50]}...")
                return True
            time.sleep(0.1)

    log("❌ 人机验证超时")
    sb.save_screenshot("turnstile_fail.png")
    return False


def extract_slug(renew_url: str) -> str:
    return renew_url.rstrip('/').split('/')[-1]


def submit_vote_api(sb, slug: str, token: str, username: str):
    body = json.dumps({
        "cf-turnstile-response": token,
        "voter_name": username,
        "ad_watched": "0"
    })
    js = f"""
        window.__vote_result__ = null;
        (async function() {{
            try {{
                var resp = await fetch('https://control.gaming4free.net/api/servers/{slug}/vote', {{
                    method: 'POST',
                    mode: 'cors',
                    credentials: 'omit',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }},
                    body: {body!r}
                }});
                var data = await resp.json();
                window.__vote_result__ = {{ http_status: resp.status, data: data }};
            }} catch(e) {{
                window.__vote_result__ = {{ http_status: 0, data: {{ success: false, message: 'fetch error: ' + e.toString() }} }};
            }}
        }})();
    """
    sb.execute_script(js)


def clear_cache_and_state(sb):
    log("🧹 清理浏览器缓存与残留 Token...")
    try:
        sb.delete_all_cookies()
        sb.execute_script("""
            try { sessionStorage.clear(); } catch(e) {}
            try { localStorage.clear(); } catch(e) {}
            window.__cf_turnstile_token__ = '';
            window.__cf_token_listener_injected__ = false;
        """)
    except Exception:
        pass


def renew_account(sb, server_name, renew_url) -> str:
    log(f"\n🎮 开始续期：{server_name}")

    username = random_mc_username()
    slug = extract_slug(renew_url)

    log("🔗 打开续期链接")
    sb.uc_open_with_reconnect(renew_url, reconnect_time=4)
    time.sleep(3)

    log("🔍 点击「VOTE」按钮，打开验证弹窗...")
    try:
        sb.wait_for_element_visible('#sd-vote-btn', timeout=15)
        sb.execute_script("document.getElementById('sd-vote-btn').scrollIntoView({block:'center'})")
        time.sleep(0.3)
        sb.click('#sd-vote-btn')
        log("✅ 已点击 VOTE 按钮，等待弹窗...")
    except Exception as e:
        log(f"❌ VOTE 按钮未找到：{e}")
        clear_cache_and_state(sb)
        return ''

    time.sleep(1)

    wait_labels = ["⏳ 等待验证组件...", "⏳ 再等验证组件...", "⏳ 三等验证组件..."]
    turnstile_ready = False
    for attempt in range(3):
        log(wait_labels[attempt])
        for _ in range(20):
            if turnstile_exists(sb):
                log("✅ 验证组件就绪")
                turnstile_ready = True
                break
            time.sleep(0.5)
        if turnstile_ready:
            break
        try:
            sb.wait_for_element_visible('#sd-vote-btn', timeout=15)
            sb.execute_script("document.getElementById('sd-vote-btn').scrollIntoView({block:'center'})")
            time.sleep(0.3)
            sb.click('#sd-vote-btn')
        except Exception as e:
            log(f"❌ VOTE 按钮未找到：{e}")
            return ''
        time.sleep(1)

    if not turnstile_ready:
        log("❌ 等待验证组件超时")
        return ''

    inject_token_listener(sb)

    if not solve_turnstile(sb):
        sb.save_screenshot(f"turnstile_fail_{server_name}.png")
        clear_cache_and_state(sb)
        return ''

    token = get_turnstile_token(sb)
    if not token:
        log(f"❌ [{server_name}] 未获取到 Turnstile Token")
        clear_cache_and_state(sb)
        return ''

    log(f"👤 用户名：{username}")
    log("📤 提交续期表单...")
    submit_vote_api(sb, slug, token, username)

    outcome = None
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            outcome = sb.execute_script("return window.__vote_result__;")
        except Exception:
            outcome = None
        if outcome:
            break
        time.sleep(0.5)

    if not outcome:
        log(f"❌ [{server_name}] 续期失败：接口无响应")
        clear_cache_and_state(sb)
        return ''

    data = outcome.get('data', {}) if isinstance(outcome, dict) else {}
    if not data.get('success'):
        msg = data.get('message', '')
        log(f"❌ [{server_name}] 续期失败，接口提示：{msg or '无'}（HTTP {outcome.get('http_status')}）")
        clear_cache_and_state(sb)
        return ''

    message  = data.get('message', '')
    vt_today = data.get('vote_count_today')
    vt_total = data.get('vote_count_total')
    try:
        secs = int(round(float(data.get('hours_remaining', 0)) * 3600))
    except Exception:
        secs = 0
    expiry_str = format_hms(secs)

    log(f"✅ 续期成功：{message}")
    log(f"📅 利用期限：{expiry_str}（今日续期 {vt_today} 次，累计 {vt_total} 次）")
    log(f"🎉 [{server_name}] 续期成功！")
    clear_cache_and_state(sb)
    return expiry_str


TARGET_SECONDS = 48 * 3600  # 48小时目标上限


def run_script():
    log("🔧 启动浏览器...")
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        log("🚀 浏览器就绪！")

        if not ACCOUNTS:
            log("❌ 未解析到任何账号，请检查 GAME4FREE_ACCOUNT 格式")
            exit(1)

        load_proxies()
        if not PROXIES:
            log("❌ 未配置代理，请检查 GAME4FREE_PROXY")
            exit(1)

        log(f"📋 共解析到 {len(ACCOUNTS)} 个账号，{len(PROXIES)} 条代理")

        proxy_index = 0
        final_tg = {}
        remaining = {name: 0 for name, _ in ACCOUNTS}

        round_num = 0
        while any(remaining[name] + 90 * 60 <= TARGET_SECONDS for name, _ in ACCOUNTS):
            round_num += 1

            if round_num > 1:
                proxy_index = (proxy_index + 1) % len(PROXIES)

            proxy_name, proxy_url = PROXIES[proxy_index]
            log(f"\n🔄 第 {round_num} 轮续期，使用代理：{proxy_name}")
            start_gost(proxy_name, proxy_url)
            log("🌐 验证出口IP...")
            try:
                sb.open("https://api.ipify.org/?format=json")
                ip_text = re.sub(r'(\d+\.\d+\.)\d+\.\d+', r'\1**.**', sb.get_text('body'))
                log(f"✅ 出口IP确认：{ip_text}")
            except Exception:
                log("⚠️ IP验证超时，跳过")

            for server_name, renew_url in ACCOUNTS:
                if remaining[server_name] + 90 * 60 > TARGET_SECONDS:
                    log(f"✅ [{server_name}] 已达48小时上限，跳过")
                    continue

                expiry = renew_account(sb, server_name, renew_url)
                if expiry:
                    new_secs = parse_countdown_seconds(expiry)
                    if new_secs > 0:
                        remaining[server_name] = new_secs
                        log(f"⏱ [{server_name}] 当前剩余：{new_secs//3600}h {(new_secs%3600)//60}m")
                    else:
                        remaining[server_name] += 90 * 60
                    final_tg[server_name] = {"expiry": expiry, "result_str": "✅ 续期成功！"}
                else:
                    if server_name not in final_tg:
                        final_tg[server_name] = {"expiry": "", "result_str": "❌ 续期失败"}

                time.sleep(2)

            stop_gost()
            if any(remaining[name] + 90 * 60 <= TARGET_SECONDS for name, _ in ACCOUNTS):
                time.sleep(20)

        log("\n🎉 所有服务器均已达到48小时，任务完成！")

    log("\n✅ 所有账号处理完毕，开始推送 TG 通知...")
    for server_name, _ in ACCOUNTS:
        info = final_tg.get(server_name, {"expiry": "", "result_str": "❌ 无记录"})
        send_tg(info["result_str"], server_name, info["expiry"], silent=True)
    log("📨 TG推送成功")


if __name__ == "__main__":
    run_script()
