#!/usr/bin/env python3
"""
Gaming4Free Renew Pro v11 - 自动续期脚本增强版
- 循环续期机制：低於目標時長時自動連續續期
- 三层点击策略 (Livewire API + Event Dispatch + Native Click)
- 广告DOM详细检测 (iframe, body text, ad elements)
- Pro成功验证 (多重判断: 倒计时/Livewire/页面刷新/奖励状态)
- 自动失败重试 + 广告卡死检测 + 页面恢复
- Livewire网络监听 + 真实method捕获 + 主动component.call()
- TG Pro详细通知
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

# ==================== Pro增强配置 ====================
TARGET_SECONDS = 45 * 3600       # 目标时长: 45小时(秒)
ADD_SECONDS = 90 * 60            # 每次续期增加: 90分钟(秒)
COOLDOWN_SEC = 120               # 冷却时间: 120秒
MAX_ROUNDS = 10                  # 最大轮次 (增加到10轮以确保达标)
AD_WAIT_SEC = 240                # 广告最大等待时间 (Pro)
VERIFY_TIMEOUT = 300             # 续期确认最长等待 (Pro)
SUCCESS_ADD_SECONDS = 3000       # 成功最低增加时间 (Pro, 50分钟)
RETRY_AFTER_FAIL = True          # 失败自动重试 (Pro)
DEBUG_PRO = True                 # Pro调试模式

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
    """【Pro】发送 Telegram 续期结果通知 - 详细格式"""
    if not TG_TOKEN or not TG_CHAT_ID: return
    msg = f"""🎮 Gaming4Free Pro

🖥服务器:
{server_name}

⏰时间:
{now_str()}

📊状态:
{result}

⏱剩余:
{expiry}

⚙️模式:
Renew-Pro v11 (Auto-Loop)
"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            log("📨 TG Pro通知成功")
    except Exception as e:
        log(f"⚠️ TG Pro推送失败: {e}")

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

def verify_extend_success(sb, before_secs):
    """
    Gaming4Free Pro续期验证 - 多重判断
    """
    log("🔍 Pro模式: 开始确认续期结果")
    start = time.time()
    while time.time() - start < VERIFY_TIMEOUT:
        try:
            text, secs = get_remaining_time(sb)
            log(f"⏱️ Pro检测: {text} ({secs-before_secs:+d}秒)")
            if secs >= before_secs + SUCCESS_ADD_SECONDS:
                screenshot(sb, "success")
                log(f"🎉 Pro确认成功: {text}")
                return True, text
            reward = sb.execute_script("let t=document.body.innerText; return t.includes('Reward') || t.includes('Watching') || t.includes('Ad');")
            if not reward: log("🎁 广告奖励状态结束")
        except Exception as e: log(f"⚠️ Pro验证异常: {e}")
        time.sleep(5)
    log("❌ Pro确认超时")
    text, secs = get_remaining_time(sb)
    return False, text

def detect_page_stuck(sb):
    """检测页面是否卡死"""
    try:
        result = sb.execute_script("return {ready: document.readyState, text: document.body ? document.body.innerText.length : 0, online: navigator.onLine};")
        if not result: return True
        if result["ready"] != "complete": return True
        if result["text"] < 50: return True
        if not result["online"]: return True
        return False
    except Exception: return True

def recover_page(sb, url):
    """页面恢复"""
    log("♻️ Pro恢复模式启动")
    try:
        sb.refresh(); time.sleep(8)
        if detect_page_stuck(sb):
            sb.open(url, timeout=30); time.sleep(8)
        log("✅ 页面恢复完成")
        return True
    except Exception as e: log(f"❌ 页面恢复失败: {e}"); return False

def setup_livewire_listener(sb):
    """拦截 Livewire 请求"""
    sb.execute_script("""
    window.__livewire_calls=[];
    const oldXHR=XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open=function(method,url){
        this._url=url; this._method=method;
        this.addEventListener("load",function(){
            try{ if(this.responseText.includes("serverMemo")){ window.__livewire_calls.push({url:this._url, method:this._method, body:this.responseText}); } }catch(e){}
        });
        return oldXHR.apply(this, arguments);
    };
    """)
    log("📡 Livewire 网络监听已启用")

def analyze_livewire(sb):
    """提取 Livewire 续期方法"""
    try:
        calls = sb.execute_script("return window.__livewire_calls || [];")
        if not calls: return None
        for item in calls:
            m = re.findall(r'"methods"\s*:\s*\[\s*"([^"]+)"', str(item))
            if m:
                for meth in m:
                    if meth not in POLLING_METHODS: return meth
    except: pass
    return None

def find_component_id_by_selector(sb, selector):
    return sb.execute_script(f"""
        var el = document.querySelector('{selector}');
        if(!el) return null;
        var comp = el.closest('[wire\\\\:id]');
        return comp ? comp.getAttribute('wire:id') : null;
    """)

def call_livewire_directly(sb, comp_id, method):
    log(f"🎯 直接调用 Livewire 方法: {method} (组件: {comp_id})")
    return sb.execute_script(f"""
        if(window.Livewire){{
            var c = Livewire.find('{comp_id}');
            if(c) {{ c.call('{method}'); return 'success'; }}
        }}
        return 'fail';
    """)

def is_driver_alive(sb):
    try: sb.driver.title; return True
    except: return False

def main():
    chrome_args = (
        "--no-sandbox,"
        "--disable-dev-shm-usage,"
        "--disable-gpu,"
        "--disable-blink-features=AutomationControlled,"
        "--window-size=1920,1080,"
        "--start-maximized"
    )

    max_browser_retries = 3
    browser_retry_delay = 10

    for server_name, server_url in ACCOUNTS:
        log(f"\n========== 开始处理服务器账号: {server_name} ==========")
        
        for browser_attempt in range(max_browser_retries):
            try:
                with SB(test=True, uc=False, headless=False, block_images=True, chromium_arg=chrome_args) as sb:
                    sb.open(server_url, timeout=30)
                    time.sleep(3)
                    
                    if GF_COOKIE:
                        for cookie in GF_COOKIE.split(";"):
                            if "=" in cookie:
                                name, value = cookie.split("=", 1)
                                sb.driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".gaming4free.net"})
                        sb.open(server_url, timeout=30)
                        time.sleep(5)

                    setup_livewire_listener(sb)
                    handle_turnstile(sb)

                    current_round = 0
                    while current_round < MAX_ROUNDS:
                        current_round += 1
                        log(f"\n🔄 --- 第 {current_round}/{MAX_ROUNDS} 轮续期流程 ---")
                        
                        before_text, before_secs = get_remaining_time(sb)
                        log(f"⏱️ 当前剩余时长: {before_text} ({before_secs}秒)")
                        
                        if before_secs >= TARGET_SECONDS:
                            log(f"✅ 目标时长已达标 ({TARGET_SECONDS//3600}小时)，停止续期")
                            break
                        
                        btn_info = check_button_cooldown(sb)
                        if btn_info and btn_info.get('cooldown'):
                            wait_time = btn_info.get('remaining', COOLDOWN_SEC)
                            log(f"⏳ 按钮冷却中，等待 {wait_time} 秒...")
                            time.sleep(wait_time + 5)
                            sb.refresh(); time.sleep(5)
                            before_text, before_secs = get_remaining_time(sb)

                        # 点击策略
                        click_done = False
                        # 策略1: 直接调用 Livewire
                        comp_id = find_component_id_by_selector(sb, 'button:contains("90")')
                        if not comp_id: comp_id = find_component_id_by_selector(sb, 'button.rt-btn-free')
                        
                        if comp_id:
                            res = call_livewire_directly(sb, comp_id, 'extend')
                            if res == 'success': click_done = True
                        
                        # 策略2: 模拟点击
                        if not click_done:
                            try:
                                sb.click('button:contains("90")', timeout=5)
                                click_done = True
                            except: pass
                        
                        if not click_done:
                            log("❌ 无法点击续期按钮，尝试刷新页面...")
                            sb.refresh(); time.sleep(5); continue

                        # 等待广告和验证
                        live_text, ad_res = wait_ad_flow(sb, before_secs, AD_WAIT_SEC)
                        ok, verify_text = verify_extend_success(sb, before_secs)
                        
                        if ok:
                            log(f"✅ 第 {current_round} 轮续期成功: {verify_text}")
                            send_tg(f"✅ 续期成功 (第{current_round}轮)", server_name, verify_text)
                        else:
                            log(f"❌ 第 {current_round} 轮续期失败")
                            send_tg(f"❌ 续期失敗 (第{current_round}轮)", server_name, verify_text)
                            recover_page(sb, server_url); time.sleep(5)
                        
                        # 每一轮结束后刷新页面，确保状态同步
                        sb.refresh(); time.sleep(5)

                    log(f"🏁 账号 {server_name} 处理结束")
                    break # 处理完当前账号，跳出浏览器重试循环

            except Exception as e:
                log(f"❌ 运行异常: {e}"); time.sleep(browser_retry_delay)

def wait_ad_flow(sb, before_secs, max_wait=AD_WAIT_SEC):
    result = {'live_text': '', 'live_secs': 0}
    t0 = time.time()
    while time.time() - t0 < max_wait:
        elapsed = time.time() - t0
        if int(elapsed) % 20 == 0 and detect_page_stuck(sb): break
        
        lt, ls = get_remaining_time(sb)
        if ls > before_secs + 3000:
            result['live_text'], result['live_secs'] = lt, ls
            break
        
        # 处理可能的冷却等待
        cooldown_info = check_button_cooldown(sb)
        if cooldown_info and cooldown_info.get('cooldown'):
            log(f"   ⏳ 按钮进入冷却，等待续期生效...")
            time.sleep(30)
            break
            
        time.sleep(2)
    return result['live_text'], result

if __name__ == "__main__":
    main()
