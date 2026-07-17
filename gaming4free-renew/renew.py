#!/usr/bin/env python3
"""
gaming4free 自动续期脚本 v5 (修复版)
- 修复: headless=False 配合 xvfb-run, 解决 uc_gui_click_captcha 崩溃
- 修复: 增加 Chrome CI 稳定性参数 (--no-sandbox, --disable-dev-shm-usage)
- 修复: 截图路径改为工作区相对路径, 与 Actions 上传路径一致
- 修复: 增加浏览器崩溃检测和重试机制
"""
import os, time, random, urllib.request, urllib.parse, re
import datetime
import traceback
from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
GF_COOKIE = os.environ.get("GAME4FREE_COOKIE", "").strip()
raw_accounts = os.environ.get("GAME4FREE_ACCOUNT", "").strip().splitlines()
ACCOUNTS = []
for line in raw_accounts:
    line = line.strip()
    if not line: continue
    parts = line.split(",", 1)
    if len(parts) == 2: ACCOUNTS.append((parts[0].strip(), parts[1].strip()))

TARGET_SECONDS = 48 * 3600
ADD_SECONDS = 90 * 60
COOLDOWN_SEC = 120
MAX_ROUNDS = 5
AD_WAIT_SEC = 100

# 【修复】截图目录改为工作区相对路径, 与 Actions upload 路径一致
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")

def now_str():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print(f"[{now_str()}] {msg}", flush=True)

def screenshot(sb, name):
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        sb.save_screenshot(os.path.join(SCREENSHOT_DIR, f"{name}.png"))
        log(f"📸 截图已保存至 {SCREENSHOT_DIR}/{name}.png")
    except Exception as e:
        log(f"⚠️ 截图失败: {e}")

def send_tg(result, server_name="", expiry=""):
    if not TG_TOKEN or not TG_CHAT_ID: return
    msg = f"🎮Game4Free 续期通知\n⏰运行时间: {now_str()}\n🖥️服务器: {server_name}\n"
    if expiry: msg += f"🔢剩余时间: {expiry}\n"
    msg += f"📊续期结果: {result}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15): log("📨 TG推送成功")
    except Exception as e: log(f"⚠️ TG推送失败: {e}")

def parse_countdown_seconds(text):
    if not text: return 0
    text = text.strip()
    parts = text.split(":")
    if len(parts) == 3:
        try: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError: pass
    h = re.search(r'(\d+)\s*h', text, re.I)
    m = re.search(r'(\d+)\s*m', text, re.I)
    total = 0
    if h: total += int(h.group(1)) * 3600
    if m: total += int(m.group(1)) * 60
    return total

def get_remaining_time(sb):
    try:
        selectors = ['[class*="timer"]', '[class*="remaining"]', '[class*="countdown"]', '#sd-timer']
        for sel in selectors:
            try:
                text = sb.execute_script(f"var el=document.querySelector('{sel}'); return el?el.textContent.trim():'';")
                if text and len(text) < 30:
                    secs = parse_countdown_seconds(text)
                    if secs > 0: return text, secs
            except Exception as e: log(f"⚠️ 获取剩余时间 (selector: {sel}) 失败: {e}")
        page_text = sb.execute_script("return document.body?document.body.innerText:'';")
        if page_text:
            match = re.search(r'(\d{1,2}:\d{2}:\d{2})', page_text)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
            match = re.search(r'(\d+h\s*\d+m)', page_text, re.I)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
    except Exception as e: log(f"⚠️ 获取剩余时间失败: {e}")
    return "", 0

def close_modals(sb):
    try:
        sels = ['button:contains("Maybe later")', '.modal-close', '[aria-label="Close"]']
        for sel in sels:
            try:
                if sb.execute_script(f"return !!document.querySelector('{sel}');"):
                    sb.click(sel); log(f"🛡️ 已关闭弹窗: {sel}"); time.sleep(1)
            except Exception as e: log(f"⚠️ 关闭弹窗 ({sel}) 失败: {e}")
    except Exception as e: log(f"⚠️ 关闭弹窗总失败: {e}")

def check_button_cooldown(sb):
    js = """
    (function() {
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var text = btns[i].innerText || '';
            if (text.indexOf('90') !== -1) {
                var disabled = btns[i].disabled || btns[i].getAttribute('aria-disabled') === 'true';
                var classes = btns[i].className || '';
                var isCooldown = classes.indexOf('disabled') !== -1 || classes.indexOf('cursor-not-allowed') !== -1 || disabled;
                var waitMatch = text.match(/Wait\s*(\d+)/i) || text.match(/(\d+)\s*s/);
                if (waitMatch) return {cooldown: true, remaining: parseInt(waitMatch[1]), text: text.trim()};
                if (isCooldown) return {cooldown: true, disabled: true, text: text.trim()};
                return {cooldown: false, text: text.trim()};
            }
        }
        return null;
    })();
    """
    try: return sb.execute_script(js)
    except Exception as e: log(f"⚠️ 检查按钮冷却失败: {e}"); return None

def handle_turnstile(sb, max_retries=3):
    for attempt in range(max_retries):
        try:
            if sb.find_elements('iframe[src*="cloudflare"]') or sb.find_elements('iframe[src*="turnstile"]'):
                log(f"🛡️ 检测到 Turnstile (尝试 {attempt+1}/{max_retries})")
                screenshot(sb, f"turnstile-{attempt}")
                try:
                    sb.uc_gui_click_captcha(); log("✅ uc_gui_click_captcha 已执行"); time.sleep(5); return True
                except Exception as e:
                    log(f"⚠️ uc_gui_click_captcha 失败: {e}")
            else:
                # 没有检测到 Turnstile, 直接返回
                return False
        except Exception as e: log(f"⚠️ Turnstile 处理异常: {e}")
        time.sleep(2)
    return False

POLLING_METHODS = ('$refresh', 'refresh', 'poll', '$poll')

def read_alpine_state(sb):
    js = """
    (function() {
        var btn = null; var all = document.querySelectorAll('button');
        for (var i = 0; i < all.length; i++) { if ((all[i].innerText || '').indexOf('90') !== -1) { btn = all[i]; break; } }
        if (!btn) return null;
        var st = {cls: btn.className || '', disabledAttr: !!btn.disabled, hasAlpine: false};
        var root = btn.closest('[x-data]') || btn;
        var d = null;
        try { if (window.Alpine && Alpine.$data) d = Alpine.$data(root); } catch(e) {}
        try { if (!d && root.__x && root.__x.$data) d = root.__x.$data; } catch(e) {}
        if (d) {
            st.hasAlpine = true;
            for (var k in d) {
                try { var v = d[k]; var tv = typeof v;
                if ((tv === 'boolean' || tv === 'number' || tv === 'string') && ('' + v).length < 60) st[k] = v;
                } catch(e) {}
            }
        }
        return st;
    })();
    """
    try: return sb.execute_script(js)
    except Exception as e: log(f"⚠️ 读取 Alpine 状态失败: {e}"); return None

def detect_ad(sb):
    js = """
    (function() {
        var vids = document.querySelectorAll('video');
        for (var i = 0; i < vids.length; i++) { if (vids[i].offsetParent !== null) return 'video'; }
        var ifs = document.querySelectorAll('iframe');
        for (var j = 0; j < ifs.length; j++) {
            var s = ((ifs[j].src || '') + ' ' + (ifs[j].id || '') + ' ' + (ifs[j].name || ''));
            if (/ads|doubleclick|reward/i.test(s) && ifs[j].offsetParent !== null) return 'iframe';
        }
        return '';
    })();
    """
    try: return sb.execute_script(js) or ''
    except Exception as e: log(f"⚠️ 检测广告失败: {e}"); return ''

def try_ad_controls(sb, ad_elapsed):
    if ad_elapsed > 20:
        try:
            sb.execute_script("""
            var els = document.querySelectorAll('[aria-label="Close"], [class*="modal"] button');
            for (var i = 0; i < els.length; i++) { if(els[i].offsetParent !== null) { els[i].click(); break; } }
            """)
            log("尝试关闭广告控制元素")
        except Exception as e: log(f"⚠️ 尝试关闭广告控制失败: {e}")

def wait_ad_flow(sb, before_secs, max_wait=AD_WAIT_SEC):
    result = {'extend_seen': False, 'reward_ready': False, 'ad_seen': False, 'live_text': '', 'live_secs': 0}
    log(f"🎬 进入广告等待流程 (最长 {max_wait}s, 期间不重载页面)...")
    t0 = time.time()
    clicked_again = False
    alpine_logged = 0
    ad_first_seen = None
    while time.time() - t0 < max_wait:
        elapsed = time.time() - t0
        try:
            calls = sb.execute_script(
                "(function(){ return (window.__reqs||[]).filter(function(r){"
                "return r.m==='POST' && /livewire/i.test(r.u) && (r.methods||[]).length>0;"
                "}).map(function(r){ return {methods: r.methods}; }); })();"
            ) or []
        except Exception as e: log(f"⚠️ 获取 Livewire 调用失败: {e}"); calls = []
        real_methods = []
        for c in calls:
            for m in (c.get('methods') or []):
                if m not in POLLING_METHODS and m not in real_methods: real_methods.append(m)
        if real_methods:
            log(f"✅ 捕获真实 Livewire 调用: method={real_methods}")
            result['extend_seen'] = True
            screenshot(sb, "extend-call")
            time.sleep(3)
            lt, ls = get_remaining_time(sb)
            if ls > before_secs + 60:
                log(f"🎉 页面已实时刷新时间: {lt}")
                result['live_text'], result['live_secs'] = lt, ls
                break
        st = read_alpine_state(sb)
        if st:
            if st.get('adRewardReady') is True and not result['reward_ready']:
                result['reward_ready'] = True
                log(f"🎁 [{int(elapsed)}s] adRewardReady=true — 广告奖励已就绪!")
            elif alpine_logged < 2:
                log(f"🔬 Alpine[{int(elapsed)}s]: 未取到组件状态")
                alpine_logged += 1
        ad = detect_ad(sb)
        if ad and not result['ad_seen']:
            result['ad_seen'] = True
            ad_first_seen = time.time()
            log(f"🎬 [{int(elapsed)}s] 检测到广告: {ad}")
            screenshot(sb, "ad-showing")
        if result['reward_ready'] and not clicked_again:
            clicked_again = True
            log("🖱️ 奖励就绪, 再次点击 +90 触发真正的续期调用...")
            try:
                WebDriverWait(sb.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., '+ 90 min')] | //button[contains(., 'watch ad')] | //button[contains(., 'Watch Ad')] | //button[contains(., 'Watch ad')] "))
                )
                sb.uc_click("button:contains('+ 90 min')", reconnect_time=4)
                log("🎯 二次点击完成")
            except Exception as e:
                log(f"⚠️ 二次点击异常: {e}")
            time.sleep(3)
            continue
        if result['ad_seen'] and ad_first_seen:
            try_ad_controls(sb, time.time() - ad_first_seen)
        if int(elapsed) % 10 == 0 and elapsed > 5:
            try:
                lt, ls = get_remaining_time(sb)
                if ls > before_secs + 60:
                    log(f"🎉 [{int(elapsed)}s] 页面时间已实时增加: {lt}")
                    result['live_text'], result['live_secs'] = lt, ls
                    break
            except Exception as e: log(f"⚠️ 实时时间检查失败: {e}")
        time.sleep(1)
    if not result['live_text']:
        lt, ls = get_remaining_time(sb)
        result['live_text'], result['live_secs'] = lt, ls
    return result['live_text'], result

def is_driver_alive(sb):
    """【新增】检测浏览器驱动是否仍然存活 - 使用更宽松的检测方式"""
    try:
        # 方法1: 尝试获取 current_url
        url = sb.driver.current_url
        if url:
            return True
    except Exception:
        pass
    try:
        # 方法2: 尝试获取 title (更宽松)
        title = sb.driver.title
        return True
    except Exception:
        pass
    try:
        # 方法3: 尝试执行简单 JS
        sb.driver.execute_script("return 1")
        return True
    except Exception:
        return False

def main():
    if not ACCOUNTS:
        log("❌ 未配置 GAME4FREE_ACCOUNT 环境变量"); return
    
    # 【修复 #7】简化的 Chrome 稳定性参数 (避免过多参数导致冲突)
    chrome_args = (
        "--no-sandbox,"
        "--disable-dev-shm-usage,"
        "--disable-gpu,"
        "--disable-gpu-sandbox,"
        "--disable-gpu-compositing,"
        "--disable-extensions,"
        "--disable-notifications,"
        "--disable-infobars,"
        "--no-first-run,"
        "--disable-default-apps,"
        "--disable-logging,"
        "--disable-sync,"
        "--disable-translate,"
        "--disable-background-networking,"
        "--disable-background-timer-throttling,"
        "--disable-renderer-backgrounding,"
        "--disable-backgrounding-occluded-windows,"
        "--disable-hang-monitor,"
        "--disable-popup-blocking,"
        "--disable-component-update,"
        "--disable-session-crashed-bubble,"
        "--disable-accelerated-compositing,"
        "--disable-accelerated-2d-canvas,"
        "--disable-accelerated-video-decode,"
        "--disable-accelerated-mjpeg-decode,"
        "--window-size=1920,1080,"
        "--start-maximized,"
        "--disable-blink-features=AutomationControlled"
    )

    # 【修复 #7】浏览器崩溃恢复机制
    max_browser_retries = 3
    browser_retry_delay = 10

    for user, pwd in ACCOUNTS:
        log(f"\n========== 开始处理账号: {user} ==========")

        for browser_attempt in range(max_browser_retries):
            sb = None
            try:
                log(f"🚀 启动浏览器 (尝试 {browser_attempt+1}/{max_browser_retries})...")

                # 【修复 #7】尝试用不同的 headless 模式
                headless_mode = "new" if browser_attempt == 0 else "old"
                
                with SB(
                    test=True,
                    uc=False,
                    headless=False,  # 【关键修复】改为 False, 由 xvfb-run 提供显示
                    proxy=os.environ.get("PROXY_SERVER") if os.environ.get("IS_PROXY") == "true" else None,
                    block_images=True,
                    settings_file=None,
                    recorder_ext=False,
                    chromium_arg=chrome_args,  # 【关键修复】CI 环境必需参数
                ) as sb:
                    log(f"🌐 尝试打开登录页面 (尝试 {browser_attempt+1}/{max_browser_retries}): https://gaming4free.net/login")
                    
                    # 【修复 #7】增加超时时间
                    try:
                        sb.open(user_server_url, timeout=30)
                    except Exception as open_err:
                        log(f"⚠️ 页面打开异常: {open_err}")
                        raise RuntimeError("页面打开失败")

                    time.sleep(3)  # 给页面更多加载时间

                    # 【修复 #7】验证浏览器是否存活
                    if not is_driver_alive(sb):
                        log("❌ 浏览器在打开页面后崩溃")
                        # 【修复 #7】尝试获取崩溃原因
                        try:
                            url = sb.driver.current_url
                            log(f"🔍 浏览器 URL: {url}")
                        except Exception as url_err:
                            log(f"🔍 无法获取浏览器 URL: {url_err}")
                        raise RuntimeError("浏览器启动后崩溃")

                    # 【修复 #7】验证页面是否加载成功
                    try:
                        title = sb.execute_script("return document.title || '';")
                        log(f"📄 页面标题: {title}")
                        if title:
                            log("✅ 页面加载成功")
                    except Exception as e:
                        log(f"⚠️ 无法获取页面标题: {e}")

                    # 注入 Cookie
                    if GF_COOKIE:
                        log("🍪 注入 Cookie...")
                        try:
                            for cookie in GF_COOKIE.split(";"):
                                if "=" in cookie:
                                    name, value = cookie.split("=", 1)
                                    cookie_dict = {"name": name.strip(), "value": value.strip(), "domain": ".gaming4free.net"}
                                    sb.driver.add_cookie(cookie_dict)
                            sb.open(user_server_url, timeout=30)
                            time.sleep(3)
                            log("✅ Cookie 注入完成")
                        except Exception as e:
                            log(f"⚠️ Cookie 注入失败: {e}")

                    const originalFetch = window.fetch;
                    window.fetch = function() {
                        return originalFetch.apply(this, arguments).then(async (response) => {
                            const clonedResponse = response.clone();
                            try {
                                const body = await clonedResponse.json();
                                window.__reqs.push({
                                    u: arguments[0],
                                    m: 'POST',
                                    methods: body.serverMemo ? body.serverMemo.data.methods : []
                                });
                            } catch (e) {}
                            return response;
                        });
                    };
                    """)
                    time.sleep(3)

                    handle_turnstile(sb)

                    # 【新增】再次验证浏览器存活
                    if not is_driver_alive(sb):
                        raise RuntimeError("浏览器在 Turnstile 处理后崩溃")

                    log(f"🔑 尝试登录账号: {user}")
                    # 先截图看页面状态
                    screenshot(sb, "before-login")
                    log("🔍 等待登录表单...")
                    try:
                        # 尝试多种方式定位邮箱输入框
                        selectors = [
                            ('name', 'email'),
                            ('name', 'username'),
                            ('placeholder', 'Email'),
                            ('placeholder', 'email'),
                            ('type', 'email'),
                        ]
                        for attr, value in selectors:
                            try:
                                sb.wait_for_element_visible(f'input[{attr}="{value}"]', timeout=5)
                                log(f"✅ 找到邮箱输入框: [{attr}='{value}']")
                                break
                            except: continue
                        else:
                            raise Exception('未找到邮箱输入框')
                    except Exception as e:
                        screenshot(sb, "no-login-form")
                        raise Exception(f"等待登录表单失败: {e}")
                    sb.type('input[name="email"]', user)
                    sb.type('input[name="password"]', pwd)
                    sb.click('button[type="submit"]')
                    time.sleep(5)
                    handle_turnstile(sb)
                    time.sleep(3)
                    close_modals(sb)

                    before_text, before_secs = get_remaining_time(sb)
                    log(f"⏱️ 续期前剩余: {before_text} ({before_secs}s)")

                    btn_info = check_button_cooldown(sb)
                    if btn_info and btn_info.get('cooldown'):
                        log(f"⏳ 按钮冷却中: {btn_info.get('text')}")
                        send_tg("按钮冷却中", user, before_text)
                        continue

                    log("🖱️ 点击 +90 按钮...")
                    try:
                        WebDriverWait(sb.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., '+ 90 min')] | //button[contains(., 'watch ad')] | //button[contains(., 'Watch Ad')] | //button[contains(., 'Watch ad')] "))
                        )
                        sb.uc_click("button:contains('+ 90 min')", reconnect_time=4)
                        log("🎯 首次点击完成")
                    except Exception as e:
                        log(f"⚠️ 首次点击失败: {e}")
                        screenshot(sb, "click-fail")
                        send_tg("点击按钮失败", user, before_text)
                        continue

                    live_text, res = wait_ad_flow(sb, before_secs)
                    if res['live_secs'] > before_secs + 60:
                        log(f"✅ 续期成功! 新时间: {live_text}")
                        send_tg("✅ 续期成功", user, live_text)
                    else:
                        log(f"❌ 续期失败或超时. 当前时间: {live_text}")
                        send_tg("❌ 续期失败", user, live_text)

            except RuntimeError as e:
                # 【修复 #7】浏览器崩溃异常，需要重试
                log(f"❌ 浏览器崩溃: {e}")
                try:
                    if sb:
                        screenshot(sb, "browser-crash")
                except:
                    pass
                
                if browser_attempt < max_browser_retries - 1:
                    log(f"⏳ 等待 {browser_retry_delay} 秒后重试浏览器...")
                    time.sleep(browser_retry_delay)
                    continue  # 继续下一次循环
                else:
                    log("❌ 浏览器连续崩溃，请检查 Chrome/Chromedriver 版本")
                    send_tg("❌ 浏览器连续崩溃", user)
                    break  # 退出重试循环，处理下一个账号
            
            except Exception as e:
                # 其他异常（不是浏览器崩溃）
                log(f"❌ 账号 {user} 执行异常: {e}\n{traceback.format_exc()}")
                # 【修复】截图保存到工作区相对路径
                try:
                    screenshot(sb, "error")
                    # 【新增】同时保存页面源码
                    with open(os.path.join(SCREENSHOT_DIR, "error.html"), "w", encoding="utf-8") as f:
                        f.write(sb.get_page_source())
                except Exception as screenshot_err:
                    log(f"⚠️ 保存调试信息失败: {screenshot_err}")
                send_tg(f"❌ 执行异常: {e}", user)
                break  # 其他异常不重试

if __name__ == "__main__":
    main()
