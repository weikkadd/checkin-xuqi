#!/usr/bin/env python3
"""
Gaming4Free 自动续期脚本 v6 (Bug修复版)
- 修复: user_server_url 未定义导致 NameError
- 修复: 正确使用 GAME4FREE_ACCOUNT 格式 (服务器名,续期URL)
- 汉化: 所有日志输出、提示信息均改为中文
"""
import os, time, random, urllib.request, urllib.parse, re
import datetime
import traceback
from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# ==================== 环境变量配置 ====================
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()          # Telegram 通知聊天ID
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()          # Telegram Bot Token
GF_COOKIE = os.environ.get("GAME4FREE_COOKIE", "").strip()     # Gaming4Free Cookie
raw_accounts = os.environ.get("GAME4FREE_ACCOUNT", "").strip().splitlines()  # 账号列表

ACCOUNTS = []
for line in raw_accounts:
    line = line.strip()
    if not line: continue
    parts = line.split(",", 1)
    if len(parts) == 2: ACCOUNTS.append((parts[0].strip(), parts[1].strip()))

# ==================== 常量定义 ====================
TARGET_SECONDS = 48 * 3600       # 目标时长: 48小时(秒)
ADD_SECONDS = 90 * 60            # 每次续期增加: 90分钟(秒)
COOLDOWN_SEC = 120               # 冷却时间: 120秒
MAX_ROUNDS = 5                   # 最大轮次
AD_WAIT_SEC = 100                # 广告等待最长时间(秒)

# 【修复】截图目录改为工作区相对路径, 与 Actions upload 路径一致
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")

def now_str():
    """获取当前格式化时间字符串"""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    """打印带时间戳的日志"""
    print(f"[{now_str()}] {msg}", flush=True)

def screenshot(sb, name):
    """截取当前页面并保存"""
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        sb.save_screenshot(os.path.join(SCREENSHOT_DIR, f"{name}.png"))
        log(f"📸 截图已保存至 {SCREENSHOT_DIR}/{name}.png")
    except Exception as e:
        log(f"⚠️ 截图失败: {e}")

def send_tg(result, server_name="", expiry=""):
    """发送 Telegram 续期结果通知"""
    if not TG_TOKEN or not TG_CHAT_ID: return
    msg = f"🎮 Game4Free 续期通知\n⏰ 运行时间: {now_str()}\n🖥️ 服务器: {server_name}\n"
    if expiry: msg += f"🔢 剩余时间: {expiry}\n"
    msg += f"📊 续期结果: {result}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15): log("📨 TG推送成功")
    except Exception as e: log(f"⚠️ TG推送失败: {e}")

def parse_countdown_seconds(text):
    """将倒计时文本解析为秒数"""
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
    """获取页面显示的剩余时间文本和秒数"""
    try:
        selectors = ['[class*="timer"]', '[class*="remaining"]', '[class*="countdown"]', '#sd-timer']
        for sel in selectors:
            try:
                text = sb.execute_script(f"var el=document.querySelector('{sel}'); return el?el.textContent.trim():'';")
                if text and len(text) < 30:
                    secs = parse_countdown_seconds(text)
                    if secs > 0: return text, secs
            except Exception as e: log(f"⚠️ 获取剩余时间 (选择器: {sel}) 失败: {e}")
        page_text = sb.execute_script("return document.body?document.body.innerText:'';")
        if page_text:
            match = re.search(r'(\d{1,2}:\d{2}:\d{2})', page_text)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
            match = re.search(r'(\d+h\s*\d+m)', page_text, re.I)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
    except Exception as e: log(f"⚠️ 获取剩余时间失败: {e}")
    return "", 0

def close_modals(sb):
    """关闭页面上的弹窗"""
    try:
        sels = ['button:contains("Maybe later")', '.modal-close', '[aria-label="Close"]']
        for sel in sels:
            try:
                if sb.execute_script(f"return !!document.querySelector('{sel}');"):
                    sb.click(sel); log(f"🛡️ 已关闭弹窗: {sel}"); time.sleep(1)
            except Exception as e: log(f"⚠️ 关闭弹窗 ({sel}) 失败: {e}")
    except Exception as e: log(f"⚠️ 关闭弹窗总失败: {e}")

def check_button_cooldown(sb):
    """检查续期按钮是否处于冷却状态"""
    js = r"""
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
    """处理 Cloudflare Turnstile 人机验证"""
    for attempt in range(max_retries):
        try:
            if sb.find_elements('iframe[src*="cloudflare"]') or sb.find_elements('iframe[src*="turnstile"]'):
                log(f"🛡️ 检测到 Cloudflare 人机验证 (第 {attempt+1}/{max_retries} 次尝试)")
                screenshot(sb, f"turnstile-{attempt}")
                try:
                    sb.uc_gui_click_captcha(); log("✅ uc_gui_click_captcha 已成功执行"); time.sleep(5); return True
                except Exception as e:
                    log(f"⚠️ uc_gui_click_captcha 执行失败: {e}")
            else:
                return False
        except Exception as e: log(f"⚠️ Turnstile 处理异常: {e}")
        time.sleep(2)
    return False

POLLING_METHODS = ('$refresh', 'refresh', 'poll', '$poll')

def read_alpine_state(sb):
    """读取 Alpine.js 组件状态"""
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
    """检测页面上是否有广告播放"""
    js = r"""
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
    """尝试关闭广告控制元素"""
    if ad_elapsed > 20:
        try:
            sb.execute_script("""
            var els = document.querySelectorAll('[aria-label="Close"], [class*="modal"] button');
            for (var i = 0; i < els.length; i++) { if(els[i].offsetParent !== null) { els[i].click(); break; } }
            """)
            log("尝试关闭广告控制元素")
        except Exception as e: log(f"⚠️ 尝试关闭广告控制失败: {e}")

def wait_ad_flow(sb, before_secs, max_wait=AD_WAIT_SEC):
    """等待广告流程完成，监控续期结果"""
    result = {'extend_seen': False, 'reward_ready': False, 'ad_seen': False, 'live_text': '', 'live_secs': 0}
    log(f"🎬 进入广告观看流程 (最长 {max_wait}秒, 期间不刷新页面)...")
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
            log(f"✅ 捕获到真实的 Livewire 续期请求: method={real_methods}")
            result['extend_seen'] = True
            screenshot(sb, "extend-call")
            time.sleep(3)
            lt, ls = get_remaining_time(sb)
            if ls > before_secs + 60:
                log(f"🎉 页面已自动刷新剩余时间: {lt}")
                result['live_text'], result['live_secs'] = lt, ls
                break
        st = read_alpine_state(sb)
        if st:
            if st.get('adRewardReady') is True and not result['reward_ready']:
                result['reward_ready'] = True
                log(f"🎁 [{int(elapsed)}秒] adRewardReady=true — 广告奖励已就绪!")
            elif alpine_logged < 2:
                log(f"🔬 Alpine框架[{int(elapsed)}秒]: 未获取到组件状态")
                alpine_logged += 1
        ad = detect_ad(sb)
        if ad and not result['ad_seen']:
            result['ad_seen'] = True
            ad_first_seen = time.time()
            log(f"🎬 [{int(elapsed)}秒] 检测到广告播放: {ad}")
            screenshot(sb, "ad-showing")
        if result['reward_ready'] and not clicked_again:
            clicked_again = True
            log("🖱️ 广告奖励已就绪, 再次点击 +90 分钟以触发真正续期...")
            try:
                WebDriverWait(sb.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., '+ 90 min')] | //button[contains(., 'watch ad')] | //button[contains(., 'Watch Ad')] | //button[contains(., 'Watch ad')] "))
                )
                # 使用标准点击方式 (uc=False 时没有 uc_click)
                btn_xpath = "//button[contains(., '+ 90 min')] | //button[contains(., 'watch ad')] | //button[contains(., 'Watch Ad')] | //button[contains(., 'Watch ad')]"
                try:
                    elem2 = sb.find_element(btn_xpath, timeout=5)
                    sb.execute_script("""arguments[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));""", elem2)
                    time.sleep(0.1)
                    sb.execute_script("""arguments[0].dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));""", elem2)
                    time.sleep(0.1)
                    sb.execute_script("""arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));""", elem2)
                except Exception:
                    pass
                log("🎯 第二次点击已完成")
            except Exception as e:
                log(f"⚠️ 第二次点击异常: {e}")
            time.sleep(3)
            continue
        if result['ad_seen'] and ad_first_seen:
            try_ad_controls(sb, time.time() - ad_first_seen)
        if int(elapsed) % 10 == 0 and elapsed > 5:
            try:
                lt, ls = get_remaining_time(sb)
                if ls > before_secs + 60:
                    log(f"🎉 [{int(elapsed)}秒] 页面时间已自动更新: {lt}")
                    result['live_text'], result['live_secs'] = lt, ls
                    break
            except Exception as e: log(f"⚠️ 实时时间检查失败: {e}")
        time.sleep(1)
    if not result['live_text']:
        lt, ls = get_remaining_time(sb)
        result['live_text'], result['live_secs'] = lt, ls
    return result['live_text'], result

def is_driver_alive(sb):
    """【新增】检测浏览器是否仍然正常运行 - 使用更宽松的检测方式"""
    try:
        url = sb.driver.current_url
        if url:
            return True
    except Exception:
        pass
    try:
        title = sb.driver.title
        return True
    except Exception:
        pass
    try:
        sb.driver.execute_script("return 1")
        return True
    except Exception:
        return False

def main():
    """主函数: 遍历所有账号执行续期"""
    if not ACCOUNTS:
        log("❌ 未配置 GAME4FREE_ACCOUNT 环境变量，请在仓库 Settings → Secrets 中添加"); return

    # Chrome 稳定性参数
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

    # 浏览器崩溃恢复机制
    max_browser_retries = 3
    browser_retry_delay = 10

    for server_name, server_url in ACCOUNTS:
        log(f"\n========== 开始处理服务器账号: {server_name} ==========")

        for browser_attempt in range(max_browser_retries):
            sb = None
            try:
                log(f"🚀 正在启动浏览器 (第 {browser_attempt+1}/{max_browser_retries} 次尝试)...")

                with SB(
                    test=True,
                    uc=False,
                    headless=False,
                    proxy=os.environ.get("PROXY_SERVER") if os.environ.get("IS_PROXY") == "true" else None,
                    block_images=True,
                    settings_file=None,
                    recorder_ext=False,
                    chromium_arg=chrome_args,
                ) as sb:
                    log(f"🌐 正在访问续期页面 (第 {browser_attempt+1}/{max_browser_retries} 次尝试): {server_url}")

                    # 打开续期页面
                    try:
                        sb.open(server_url, timeout=30)
                    except Exception as open_err:
                        log(f"⚠️ 页面加载异常: {open_err}")
                        raise RuntimeError("页面打开失败，请检查网络或代理设置")

                    time.sleep(3)

                    # 验证浏览器是否存活
                    if not is_driver_alive(sb):
                        log("❌ 浏览器在打开页面后意外停止响应")
                        try:
                            url = sb.driver.current_url
                            log(f"🔍 浏览器当前地址: {url}")
                        except Exception as url_err:
                            log(f"🔍 无法获取浏览器地址: {url_err}")
                        raise RuntimeError("浏览器启动后意外停止，请检查资源是否充足")

                    # 验证页面是否加载成功
                    try:
                        title = sb.execute_script("return document.title || '';")
                        log(f"📄 当前页面标题: {title}")
                        if title:
                            log("✅ 页面加载成功")
                    except Exception as e:
                        log(f"⚠️ 无法读取页面标题: {e}")

                    # 注入 Cookie
                    if GF_COOKIE:
                        log("🍪 正在注入浏览器 Cookie 凭证...")
                        try:
                            for cookie in GF_COOKIE.split(";"):
                                if "=" in cookie:
                                    name, value = cookie.split("=", 1)
                                    cookie_dict = {"name": name.strip(), "value": value.strip(), "domain": ".gaming4free.net"}
                                    sb.driver.add_cookie(cookie_dict)
                            sb.open(server_url, timeout=30)
                            time.sleep(3)
                            log("✅ Cookie 凭证注入完成")
                        except Exception as e:
                            log(f"⚠️ Cookie 注入失败: {e}")

                    # 拦截 Livewire 请求
                    sb.execute_script("""
                    window.__reqs = [];
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

                    # 再次验证浏览器存活
                    if not is_driver_alive(sb):
                        raise RuntimeError("浏览器在处理人机验证后意外停止")

                    log(f"🔑 准备执行账号操作: {server_name}")

                    # 【关键修复】等待 Livewire/Alpine 组件完全渲染
                    log("⏳ 等待页面组件完全加载 (最多15秒)...")
                    rendered = False
                    for i in range(15):
                        try:
                            page_text = sb.execute_script("return document.body?document.body.innerText:'';")
                            if '+90' in page_text or 'watch ad' in page_text.lower():
                                rendered = True
                                log(f"✅ 续期按钮已渲染 (耗时{i+1}秒)")
                                break
                        except Exception:
                            pass
                        time.sleep(1)

                    if not rendered:
                        log("⚠️ 超时未检测到续期按钮，尝试向下滚动触发懒加载...")
                        sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                        sb.execute_script("window.scrollTo(0, 0);")
                        time.sleep(2)

                    screenshot(sb, "before-login")

                    before_text, before_secs = get_remaining_time(sb)
                    log(f"⏱️ 续期前剩余时长: {before_text} ({before_secs}秒)")

                    btn_info = check_button_cooldown(sb)
                    if btn_info and btn_info.get('cooldown'):
                        log(f"⏳ 续期按钮冷却中: {btn_info.get('text')}")
                        send_tg("按钮冷却中", server_name, before_text)
                        continue

                    log("🖱️ 正在寻找并点击 +90 分钟续期按钮...")

                    # 策略1: SeleniumBase movement_click (带鼠标轨迹，最接近真人操作)
                    click_done = False
                    try:
                        log("📍 尝试 movement_click...")
                        elem = sb.find_element('//button[contains(text(), "+90")] | //button[contains(text(), "90 min")]', timeout=10)
                        elem.location_once_scrolled_into_view
                        sb.movement_click(elem)
                        log("✅ movement_click 成功")
                        click_done = True
                    except Exception as e:
                        log(f"⚠️ movement_click 失败: {e}")

                    # 策略2: sb.click() 标准点击
                    if not click_done:
                        try:
                            log("📍 尝试 sb.click()...")
                            sb.click('//button[contains(text(), "+90")] | //button[contains(text(), "90 min")]', timeout=5)
                            log("✅ sb.click() 成功")
                            click_done = True
                        except Exception as e:
                            log(f"⚠️ sb.click() 失败: {e}")

                    # 策略2: driver.findElement + JavaScript click（绕过 sb.click 的参数限制）
                    if not click_done:
                        try:
                            log("📍 尝试 driver.findElements + JS click...")
                            js_result = sb.execute_script("""
                                var allBtns = document.querySelectorAll('button');
                                for (var i = 0; i < allBtns.length; i++) {
                                    var text = (allBtns[i].textContent || '').trim();
                                    if (text.indexOf('90') !== -1) {
                                        // 确保按钮可见且可交互
                                        allBtns[i].style.pointerEvents = 'auto';
                                        allBtns[i].style.visibility = 'visible';
                                        allBtns[i].style.opacity = '1';
                                        allBtns[i].removeAttribute('disabled');
                                        allBtns[i].classList.remove('opacity-50', 'cursor-not-allowed');

                                        // scrollIntoView
                                        allBtns[i].scrollIntoView({behavior: 'instant', block: 'center'});

                                        // 获取 Alpine.js / Livewire 绑定的数据
                                        var root = allBtns[i];
                                        var alpineData = null;
                                        while (root && !alpineData) {
                                            try {
                                                if (window.Alpine && Alpine.$data) alpineData = Alpine.$data(root);
                                                else if (root.__x && root.__x.$data) alpineData = root.__x.$data;
                                            } catch(e) {}
                                            if (!alpineData) root = root.parentElement;
                                        }

                                        if (alpineData) {
                                            console.log('Alpine keys:', Object.keys(alpineData).slice(0,8));
                                        }

                                        // 关键：检查按钮是否有 @click 或 wire:click 属性
                                        var hasWireClick = allBtns[i].hasAttribute('wire:click') 
                                            || allBtns[i].hasAttribute('@click')
                                            || allBtns[i].hasAttribute('x-on:click');

                                        // 如果有 Livewire 绑定，先触发 livewire 事件再 click
                                        if (hasWireClick) {
                                            // 手动触发 Livewire 的 dispatchEvent
                                            var eventName = null;
                                            if (allBtns[i].hasAttribute('wire:click')) {
                                                eventName = allBtns[i].getAttribute('wire:click');
                                            } else if (allBtns[i].hasAttribute('@click')) {
                                                eventName = allBtns[i].getAttribute('@click').replace(/'/g,'').replace(/"/g,'');
                                            }

                                            if (eventName) {
                                                console.log('Found Livewire event:', eventName);
                                                // 通过 Livewire 组件发送事件
                                                var component = window.Livewire ? window.Livewire.find(allBtns[i].closest('[wire:id]').getAttribute('wire:id')) : null;
                                                if (component) {
                                                    component.dispatch(event => { /* no-op */ });
                                                }
                                            }
                                        }

                                        // 最后直接调用原生 click
                                        allBtns[i].click();
                                        return 'clicked:' + text.substring(0,20) + '|wire:' + hasWireClick + '|' + (eventName||'none');
                                    }
                                }
                                return 'not-found';
                            """)
                            log(f"🎯 JS click 结果: {js_result}")
                            if 'clicked' in js_result:
                                click_done = True
                        except Exception as e:
                            log(f"⚠️ driver.findElements 失败: {e}")

                    # 策略3: 最后用 JS click() 直接调用（绕过所有事件系统）
                    if not click_done:
                        try:
                            log("📍 尝试 JS 直接 click()...")
                            js_result = sb.execute_script("""
                                var btns = document.querySelectorAll('button');
                                for (var i = 0; i < btns.length; i++) {
                                    if ((btns[i].textContent || '').indexOf('90') !== -1) {
                                        btns[i].scrollIntoView({block: 'center'});
                                        // 先检查是否有 Alpine.js / Livewire 绑定的事件
                                        var alpineData = null;
                                        var root = btns[i];
                                        while (root && !alpineData) {
                                            try {
                                                if (window.Alpine && Alpine.$data) alpineData = Alpine.$data(root);
                                                else if (root.__x && root.__x.$data) alpineData = root.__x.$data;
                                            } catch(e) {}
                                            if (!alpineData) root = root.parentElement;
                                        }
                                        if (alpineData) {
                                            console.log('Found Alpine data with methods:', Object.keys(alpineData).slice(0,5));
                                        }
                                        // 清除可能阻止点击的样式
                                        btns[i].style.pointerEvents = 'auto';
                                        btns[i].style.visibility = 'visible';
                                        btns[i].style.opacity = '1';
                                        btns[i].removeAttribute('disabled');
                                        // 直接调用原生 click
                                        btns[i].click();
                                        return 'clicked:' + (btns[i].textContent || '').trim().substring(0,20);
                                    }
                                }
                                return 'not-found';
                            """)
                            log(f"🎯 JS 点击结果: {js_result}")
                            if 'clicked' in js_result:
                                click_done = True
                        except Exception as e:
                            log(f"⚠️ JS 点击异常: {e}")

                    if not click_done:
                        log("❌ 所有点击策略均失败")
                        screenshot(sb, "点击全部失败")
                        send_tg("❌ 无法点击续期按钮", server_name, before_text)
                        continue

                    # 点击后等待页面响应
                    log("⏳ 等待页面响应 (最多10秒)...")
                    responded = False
                    for wi in range(10):
                        time.sleep(1)
                        page_after = sb.execute_script("return document.body?document.body.innerText:'';")
                        match_new = re.search(r'(\d+:){2}\d+', page_after)
                        if match_new:
                            new_secs = parse_countdown_seconds(match_new.group(0))
                            if new_secs > before_secs + 30:
                                log(f"✅ 页面已响应！新时间: {match_new.group(0)}")
                                responded = True
                                break

                    if not responded:
                        log("ℹ️ 页面未在10秒内明显变化，继续检查 Turnstile...")

                    screenshot(sb, "after-click-pre-check")

                    # 检测并处理 Cloudflare Turnstile 弹窗
                    log("🛡️ 检查 Turnstile...")
                    def check_turnstile_present():
                        return bool(sb.execute_script("""
                            return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                || !!document.querySelector('.cf-turnstile')
                                || !!document.querySelector('[class*="turnstile-"]')
                                || !!document.querySelector('[data-testid="turnstile-widget"]')
                                || !!document.querySelector('[aria-label="Security verification"]');
                        """))

                    if check_turnstile_present():
                        log("⏳ 检测到 Turnstile 弹窗！")
                        screenshot(sb, "turnstile-detected")
                        sb.execute_script("""
                            var turnstiles = document.querySelectorAll('.cf-turnstile > div');
                            for (var t = 0; t < turnstiles.length; t++) {
                                var boxes = turnstiles[t].querySelectorAll('span[role="checkbox"]');
                                if (boxes.length > 0) { boxes[0].click(); break; }
                            }
                            if (turnstiles.length > 0) { turnstiles[0].click(); }
                        """)
                        for vi in range(15):
                            time.sleep(1)
                            if not check_turnstile_present():
                                log(f"✅ Turnstile 验证已通过 ({vi+1}秒)")
                                break
                        else:
                            log("⚠️ Turnstile 验证超时")
                            screenshot(sb, "turnstile-timeout")
                    else:
                        log("✅ 未检测到 Turnstile")

                    live_text, res = wait_ad_flow(sb, before_secs)
                    if res['live_secs'] > before_secs + 60:
                        log(f"✅ 续期成功！新剩余时间: {live_text}")
                        send_tg("✅ 续期成功！", server_name, live_text)
                    else:
                        log(f"❌ 续期失败或超时。当前时间: {live_text}")
                        send_tg("❌ 续期失败", server_name, live_text)

            except RuntimeError as e:
                log(f"❌ 浏览器进程崩溃: {e}")
                try:
                    if sb:
                        screenshot(sb, "浏览器崩溃截图")
                except:
                    pass

                if browser_attempt < max_browser_retries - 1:
                    log(f"⏳ 等待 {browser_retry_delay} 秒后重新启动浏览器...")
                    time.sleep(browser_retry_delay)
                    continue
                else:
                    log("❌ 浏览器连续崩溃，请检查 Chrome 和 Chromedriver 版本是否匹配")
                    send_tg("❌ 浏览器连续崩溃", server_name)
                    break

            except Exception as e:
                log(f"❌ 服务器 '{server_name}' 执行过程中发生异常: {e}\n{traceback.format_exc()}")
                try:
                    screenshot(sb, "错误截图")
                    with open(os.path.join(SCREENSHOT_DIR, "error.html"), "w", encoding="utf-8") as f:
                        f.write(sb.get_page_source())
                except Exception as screenshot_err:
                    log(f"⚠️ 保存调试信息失败: {screenshot_err}")
                send_tg(f"❌ 执行异常: {e}", server_name)
                break

if __name__ == "__main__":
    main()
