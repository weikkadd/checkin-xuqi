#!/usr/bin/env python3
"""
Gaming4Free Renew Pro v10 - 自动续期脚本增强版
- 三层点击策略 (Livewire API + Event Dispatch + Native Click)
- 广告DOM详细检测 (iframe, body text, ad elements)
- Pro成功验证 (多重判断: 倒计时/Livewire/页面刷新/奖励状态)
- 自动失败重试 + 广告卡死检测 + 页面恢复
- Livewire网络监听 + 真实method捕获 + 主动component.call()
- TG Pro详细通知
- Turnstile 实时监控 + CDP 真实点击 + UC 模式
"""
import os, time, random, urllib.request, urllib.parse, re
import datetime
import traceback
import subprocess
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
TARGET_SECONDS = 48 * 3600       # 目标时长: 48小时(秒)
ADD_SECONDS = 90 * 60            # 每次续期增加: 90分钟(秒)
COOLDOWN_SEC = 120               # 冷却时间: 120秒
MAX_ROUNDS = 5                   # 最大轮次
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
    # Mask email for privacy: show first 2 and last 2 chars
    masked = server_name[:2] + '****' + server_name[-2:] if len(server_name) > 4 else server_name
    msg = f"""🎮Gaming4Free Pro
🖥️服务器: {server_name}
⏰时间: {now_str()}
📊状态: {result}
⏱剩余: {expiry}
⚙️模式: Renew-Pro v10
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
    """获取页面显示的剩余时间文本和秒数 - 精确匹配到期时间"""
    try:
        page_text = sb.execute_script("(function(){ return document.body?document.body.innerText:''; })()")
        if not page_text:
            return "", 0
        
        # === 策略1: 查找包含 expire/remaining/end 关键词附近的时间 ===
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            lower_line = line.lower().strip()
            if any(kw in lower_line for kw in ['expire', 'remaining', 'ends', 'due', '到期', '剩余']):
                time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
                if time_match:
                    t = time_match.group(1)
                    s = parse_countdown_seconds(t)
                    if s > 0: return t, s
                hms_match = re.search(r'(\d+\s*h\s*\d+\s*m)', line, re.I)
                if hms_match:
                    t = hms_match.group(1).strip()
                    s = parse_countdown_seconds(t)
                    if s > 0: return t, s
                for j in range(max(0, i-1), min(len(lines), i+3)):
                    tm = re.search(r'(\d{1,2}:\d{2}:\d{2})', lines[j])
                    if tm:
                        t = tm.group(1)
                        s = parse_countdown_seconds(t)
                        if s > 0: return t, s
                    hm = re.search(r'(\d+\s*h\s*\d+\s*m)', lines[j], re.I)
                    if hm:
                        t = hm.group(1).strip()
                        s = parse_countdown_seconds(t)
                        if s > 0: return t, s
        
        # === 策略2: 使用 CSS 选择器查找明确的到期时间元素 ===
        css_selectors = [
            '[class*="expire"]',
            '[class*="remaining"]',
            '[class*="countdown"]',
            '[data-testid*="expire"]',
            '[data-testid*="remaining"]',
            '[data-testid*="timer"]',
            '#sd-timer',
        ]
        for sel in css_selectors:
            try:
                text = sb.execute_script(f"(function(){{ var el=document.querySelector('{sel}'); return el?el.textContent.trim():''; }})()")
                if text and len(text) < 50:
                    secs = parse_countdown_seconds(text)
                    if secs > 0: return text, secs
            except:
                pass
        
        # === 策略3: 匹配所有 Xh Ym 格式的时间，排除 uptime 上下文 ===
        all_hm_matches = re.findall(r'(\d+\s*h\s*\d+\s*m)', page_text, re.I)
        for m in all_hm_matches:
            t = m.strip()
            s = parse_countdown_seconds(t)
            if s > 0 and s < 86400 * 365:
                idx = page_text.find(t)
                context = page_text[max(0,idx-30):idx+30].lower()
                if 'uptime' not in context and 'up time' not in context:
                    return t, s
        
        # === 策略4: 回退到第一个 HH:MM:SS 格式 ===
        match = re.search(r'(\d{1,2}:\d{2}:\d{2})', page_text)
        if match:
            return match.group(1), parse_countdown_seconds(match.group(1))
        
    except Exception as e:
        log(f"⚠️ 获取剩余时间失败: {e}")
    return "", 0

def close_modals(sb):
    """关闭页面上的弹窗"""
    try:
        sels = ['button:contains("Maybe later")', '.modal-close', '[aria-label="Close"]']
        for sel in sels:
            try:
                if sb.execute_script("return !!document.querySelector(arguments[0]);", sel):
                    sb.click(sel); log(f"🛡️ 已关闭弹窗: {sel}"); time.sleep(1)
            except Exception as e: log(f"⚠️ 关闭弹窗 ({sel}) 失败: {e}")
    except Exception as e: log(f"⚠️ 关闭弹窗总失败: {e}")

def check_button_cooldown(sb):
    """检查续期按钮是否处于冷却状态"""
    # === 策略1: 检查页面上的 "expires XX:XX" 冷却文本 ===
    try:
        page_text = sb.execute_script("(function(){ return document.body?document.body.innerText:''; })()")
        if page_text:
            exp_match = re.search(r'expires\s+(\d+\S+)', page_text, re.I)
            if exp_match:
                exp_text = exp_match.group(0).strip()
                # 匹配 HH:MM 格式 (如 "expires 20:00" 表示 20分钟)
                hm_match = re.search(r'(\d+):(\d+)', exp_text)
                if hm_match:
                    hours = int(hm_match.group(1))
                    mins = int(hm_match.group(2))
                    remaining_sec = hours * 3600 + mins * 60
                    log(f"⏳ 检测到续费冷却: {exp_text} (剩余 {remaining_sec}秒 = {hours}h{mins}m)")
                    return {'cooldown': True, 'remaining': remaining_sec, 'text': exp_text}
                # 匹配纯数字格式 (如 "expires 5m", "expires 2h")
                num_match = re.search(r'(\d+)', exp_text)
                if num_match:
                    val = int(num_match.group(1))
                    if 'd' in exp_text.lower():
                        remaining_sec = val * 86400
                    elif 'h' in exp_text.lower():
                        remaining_sec = val * 3600
                    elif 'm' in exp_text.lower():
                        remaining_sec = val * 60
                    else:
                        remaining_sec = val
                    log(f"⏳ 检测到续费冷却: {exp_text} (剩余 {remaining_sec}秒)")
                    return {'cooldown': True, 'remaining': remaining_sec, 'text': exp_text}
            # 匹配 "XX:XX cd" 格式 (如 "04:56 cd" 表示按钮冷却倒计时)
            cd_match = re.search(r'(\d+):(\d+)\s+cd', page_text, re.I)
            if cd_match:
                mins = int(cd_match.group(1))
                secs = int(cd_match.group(2))
                remaining_sec = mins * 60 + secs
                cd_text = cd_match.group(0).strip()
                log(f"⏳ 检测到按钮冷却倒计时: {cd_text} (剩余 {remaining_sec}秒)")
                return {'cooldown': True, 'remaining': remaining_sec, 'text': cd_text}
    except Exception as e:
        log(f"⚠️ 检查 expires 冷却失败: {e}")
    
    # === 策略2: 检查按钮本身的 disabled 状态 ===
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
    """处理 Cloudflare Turnstile 人机验证 (Pro增强版)"""
    for attempt in range(max_retries):
        try:
            if sb.find_elements('iframe[src*="cloudflare"]') or sb.find_elements('iframe[src*="turnstile"]'):
                log(f"🛡️ 检测到 Cloudflare 人机验证 (第 {attempt+1}/{max_retries} 次尝试)")
                screenshot(sb, f"turnstile-{attempt}")
                
                # 1. 优先尝试 UC 模式的原生点击 (isTrusted=true)
                try:
                    sb.uc_gui_click_captcha()
                    log("✅ uc_gui_click_captcha 已成功执行")
                    time.sleep(5)
                    if not sb.find_elements('iframe[src*="cloudflare"]'): return True
                except Exception as e:
                    log(f"⚠️ uc_gui_click_captcha 执行失败: {e}")

                # 2. 尝试使用 xdotool 进行底层系统点击 (绕过 CDP 检测)
                try:
                    cf_iframes = sb.find_elements('iframe[src*="challenges.cloudflare.com"]') or \
                                 sb.find_elements('iframe[src*="cloudflare"]')
                    if cf_iframes:
                        iframe = cf_iframes[0]
                        rect = sb.execute_script(
                            "(function() { var el = arguments[0]; var r = el.getBoundingClientRect(); "
                            "return {x: r.x, y: r.y, w: r.width, h: r.height}; })();",
                            iframe
                        )
                        if rect and rect.get('w', 0) > 0:
                            # 点击 checkbox 区域 (iframe 左侧 30px)
                            click_x = int(rect['x'] + 30)
                            click_y = int(rect['y'] + rect['h'] / 2)
                            log(f"📍 xdotool 尝试点击坐标: ({click_x}, {click_y})")
                            subprocess.run(["xdotool", "mousemove", str(click_x), str(click_y)], check=False)
                            time.sleep(0.2)
                            subprocess.run(["xdotool", "click", "1"], check=False)
                            time.sleep(5)
                            if not sb.find_elements('iframe[src*="cloudflare"]'): return True
                except Exception as ex:
                    log(f"⚠️ xdotool 点击异常: {ex}")

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
            var s = ((ifs[j].src || "") + " " + (ifs[j].id || "") + " " + (ifs[j].name || ""));
            if (/ads|doubleclick|reward/i.test(s) && ifs[j].offsetParent !== null) return 'iframe';
        }
        if (document.body && document.body.innerText.includes('seconds until reward')) return 'text_reward_timer';
        return '';
    })();
    """
    try: return sb.execute_script(js) or ''
    except Exception as e: log(f"⚠️ 检测广告失败: {e}"); return ''

def try_ad_controls(sb, ad_elapsed):
    """尝试关闭广告控制元素"""
    # 增加对 "seconds until reward" 计时器和关闭按钮的检测
    try:
        # 检查是否有 "seconds until reward" 文本
        reward_timer_text = sb.execute_script("""
            return (function() {
                let el = document.querySelector('div:has(> span:not([class*="hidden"]) + span:not([class*="hidden"]) + span:not([class*="hidden"]))');
                if (el && el.innerText.includes('seconds until reward')) {
                    return el.innerText;
                }
                return '';
            })();
        """)
        if reward_timer_text:
            log(f"⏱️ 检测到广告计时器: {reward_timer_text}")
            # 提取秒数
            match = re.search(r'(\d+)\s*seconds until reward', reward_timer_text)
            if match:
                remaining_seconds = int(match.group(1))
                if remaining_seconds <= 1: # 接近0秒时，尝试点击关闭按钮
                    log("🎯 广告即将结束，尝试点击关闭按钮...")
                    # 尝试点击 X 按钮 (截图中的样式)
                    try:
                        sb.execute_script("""
                            return (function() {
                                let closeBtn = document.querySelector('div:has(> span:not([class*="hidden"]) + span:not([class*="hidden"]) + span:not([class*="hidden"])) > button');
                                if (closeBtn && closeBtn.innerText.includes('X')) {
                                    closeBtn.click();
                                    return true;
                                }
                                return false;
                            })();
                        """)
                        log("✅ 成功点击广告关闭按钮 (X)")
                        return True
                    except Exception as e:
                        log(f"⚠️ 点击广告关闭按钮 (X) 失败: {e}")

        # 原有的关闭广告控制元素逻辑
        if ad_elapsed > 20:
            sb.execute_script("""
            var els = document.querySelectorAll('[aria-label="Close"], [class*="modal"] button');
            for (var i = 0; i < els.length; i++) { if(els[i].offsetParent !== null) { els[i].click(); break; } }
            """)
            log("尝试关闭广告控制元素")
            return True
    except Exception as e: log(f"⚠️ 尝试关闭广告控制失败: {e}")
    return False


# ================================================================
# Pro v7: 成功验证 + 页面恢复 + 广告卡死检测
# ================================================================

def verify_extend_success(sb, before_secs):
    """
    Gaming4Free Pro续期验证 - 多重判断
    1. 倒计时增加
    2. Livewire完成
    3. 页面刷新
    4. 奖励状态消失
    """
    log("🔍 Pro模式: 开始确认续期结果")
    start = time.time()

    while time.time() - start < VERIFY_TIMEOUT:
        try:
            text, secs = get_remaining_time(sb)
            log(f"⏱️ Pro检测: {text} ({secs-before_secs:+d}秒)")

            # 时间增加达到阈值
            if secs >= before_secs + SUCCESS_ADD_SECONDS:
                screenshot(sb, "success")
                log(f"🎉 Pro确认成功: {text}")
                return True, text

            # 检查Livewire活动
            req = sb.execute_script("(function(){ return window.__reqs || []; })()")
            if req:
                log("📡 检测到Livewire活动")

            # 检查奖励按钮状态
            reward = sb.execute_script("""
            return (function() {
                let t=document.body.innerText;
                return t.includes('Reward') || t.includes('Watching') || t.includes('Ad');
            })();
            """)
            if not reward:
                log("🎁 广告奖励状态结束")

        except Exception as e:
            log(f"⚠️ Pro验证异常: {e}")

        time.sleep(5)

    log("❌ Pro确认超时")
    screenshot(sb, "verify-timeout")
    text, secs = get_remaining_time(sb)
    return False, text


def detect_page_stuck(sb):
    """检测页面是否卡死"""
    try:
        result = sb.execute_script("""
        return (function() {
            return {
                ready: document.readyState,
                text: document.body ? document.body.innerText.length : 0,
                online: navigator.onLine
            };
        })();
        """)
        if not result: return True
        if result["ready"] != "complete": return True
        # Gaming4Free uses Livewire rendering; innerText can be small initially
        # Only flag as stuck if text is truly empty (no meaningful content)
        if result["text"] < 10: return True
        if not result["online"]: return True
        return False
    except Exception:
        return True


def recover_page(sb, url):
    """页面恢复"""
    log("♻️ Pro恢复模式启动")
    try:
        screenshot(sb, "before-recover")
        sb.refresh()
        time.sleep(8)

        # 检查页面
        if detect_page_stuck(sb):
            log("⚠️ 刷新后仍异常，重新打开页面")
            sb.open(url, timeout=30)
            time.sleep(8)

        screenshot(sb, "after-recover")
        log("✅ 页面恢复完成")
        return True
    except Exception as e:
        log(f"❌ 页面恢复失败: {e}")
        return False


# ================================================================
# Pro v8: Livewire 网络监听 + 真实method捕获 + 主动调用
# ================================================================

def setup_livewire_listener(sb):
    """拦截 Livewire 请求 - 捕获真实 method 和 wire:id"""
    sb.execute_script("""
    window.__livewire_calls=[];
    const oldFetch=window.fetch;
    window.fetch=function(){
        let args=arguments;
        return oldFetch.apply(this,args)
        .then(async function(resp){
            try{
                let clone=resp.clone();
                let json=await clone.json();
                window.__livewire_calls.push({
                    url:args[0],
                    time:Date.now(),
                    data:json
                });
            }catch(e){}
            return resp;
        });
    };
    const oldXHR=XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open=function(method,url){
        this._url=url;
        this._method=method;
        this.addEventListener("load",function(){
            try{
                if(this.responseText.includes("serverMemo")){
                    window.__livewire_calls.push({
                        url:this._url,
                        method:this._method,
                        body:this.responseText
                    });
                }
            }catch(e){}
        });
        return oldXHR.apply(this, arguments);
    };
    """)
    log("📡 Livewire 网络监听已启用")


def analyze_livewire(sb):
    """
    自动寻找真实续期方法
    从 __livewire_calls 中提取包含 serverMemo 的请求
    """
    try:
        calls = sb.execute_script("(function(){ return window.__livewire_calls || []; })()")
        if not calls: return None

        for item in calls:
            text = str(item)

            # 找 method 数组
            m = re.findall(r'"methods"\s*:\s*\[\s*"([^"]+)"', text)
            if m:
                for meth in m:
                    if meth not in POLLING_METHODS: return meth
        return None
    except Exception: return None


def find_component_id_by_selector(sb, selector):
    """根据选择器寻找 wire:id"""
    try:
        return sb.execute_script(
            "return (function() { " +
            "let el=document.querySelector(arguments[0]); " +
            "if(!el) return null; " +
            "let comp=el.closest('[wire\\:id]'); " +
            "return comp?comp.getAttribute('wire:id'):null; " +
            "})();"
            , selector
        )
    except Exception: return None


def call_livewire_directly(sb, component_id, method):
    """【Pro v8】直接调用 Livewire 組件方法"""
    try:
        log(f"🚀 尝试直接调用 Livewire: component={component_id}, method={method}")
        js_script = """
            return (function() {
                if(window.Livewire){
                    let comp=Livewire.find('{component_id_placeholder}');
                    if(comp){
                        comp.call('{method_placeholder}');
                        return 'called-via-find';
                    }
                    let comps=Livewire.all();
                    for(let c of comps){
                        if(c.id==='{component_id_placeholder}'){
                            c.call('{method_placeholder}');
                            return 'called-via-all';
                        }
                    }
                }
                return 'no-livewire';
            })();
        """.format(component_id_placeholder=component_id, method_placeholder=method)
        res = sb.execute_script(js_script)
        log(f"🎯 直接调用结果: {res}")
        return True
    except Exception as e:
        log(f"⚠️ 直接调用失败: {e}")
        return False


# ================================================================
# 主程序逻辑
# ==================== 主程序逻辑 ====================

def main():
    if not ACCOUNTS:
        log("❌ 未配置任何账号，请检查环境变量 GAME4FREE_ACCOUNT")
        return

    max_browser_retries = 3
    browser_retry_delay = 10

    # 预先清理可能的旧截图
    if os.path.exists(SCREENSHOT_DIR):
        try:
            import shutil
            shutil.rmtree(SCREENSHOT_DIR)
            log("🧹 已清理旧的调试截图目录")
        except: pass

    # 浏览器启动参数
    chrome_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--disable-blink-features=AutomationControlled",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]

    for server_name, server_url in ACCOUNTS:
        log(f"\n========== 开始处理服务器账号: {server_name} ==========")

        account_finished = False
        for browser_attempt in range(max_browser_retries):
            sb = None
            try:
                log(f"🚀 正在启动浏览器 (第 {browser_attempt+1}/{max_browser_retries} 次尝试)...")

                with SB(
                    test=True,
                    uc=True,
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
                    try:
                        title = sb.get_title()
                        log(f"📄 当前页面标题: {title}")
                        log("✅ 页面加载成功")
                    except Exception as e:
                        log(f"❌ 浏览器连接丢失: {e}")
                        raise RuntimeError("浏览器启动后立即失效")

                    # 注入 Cookie
                    if GF_COOKIE:
                        log("🍪 正在注入浏览器 Cookie 凭证...")
                        try:
                            # 尝试解析多个 Cookie (格式: name1=val1; name2=val2)
                            cookies = GF_COOKIE.split(';')
                            for c in cookies:
                                c = c.strip()
                                if '=' in c:
                                    name, value = c.split('=', 1)
                                    sb.add_cookie({'name': name, 'value': value, 'domain': '.gaming4free.net'})
                            log("✅ Cookie 凭证注入完成")
                            sb.refresh()
                            time.sleep(5)
                        except Exception as e:
                            log(f"⚠️ Cookie 注入失败: {e}")

                    # 启用网络监听
                    setup_livewire_listener(sb)

                    log("⏳ 等待 Livewire/Alpine 组件完全挂载...")
                    for _ in range(10):
                        has_lw = sb.execute_script("(function(){ return !!window.Livewire; })()")
                        if has_lw: break
                        time.sleep(1)
                    log(f"✅ 组件已挂载 ({_ + 1}秒)")

                    log(f"🔑 准备执行账号操作: {server_name}")

                    # 等待续期按钮出现
                    log("⏳ 等待页面组件完全加载 (最多15秒)...")
                    try:
                        sb.wait_for_element('button.rt-btn-free', timeout=15)
                    except:
                        log("⚠️ 超时未检测到续期按钮，尝试向下滚动触发懒加载...")
                        sb.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                        time.sleep(3)
                        sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)

                    screenshot(sb, "before-login")

                    # 获取当前时间
                    before_text, before_secs = get_remaining_time(sb)
                    log(f"⏱️ 续期前剩余时长: {before_text} ({before_secs}秒)")
                    # 诊断：获取页面完整文本
                    page_text = sb.execute_script("(function(){ return document.body?document.body.innerText:''; })()")
                    time_matches = re.findall(r'(\d{1,2}:\d{2}:\d{2})', page_text)
                    if time_matches:
                        log(f"🔍 页面中发现的时间: {time_matches[:3]}")

                    # 检查是否需要续期
                    if before_secs > TARGET_SECONDS:
                        log(f"✅ 剩余时间充足 ({before_text} > 48h)，跳过续期")
                        send_tg("✅ 时间充足", server_name, before_text)
                        account_finished = True
                        break

                    # 检查按钮冷却
                    cooldown_info = check_button_cooldown(sb)
                    if cooldown_info and cooldown_info.get('cooldown'):
                        rem = cooldown_info.get('remaining', '?')
                        log(f"⏳ 续期按钮处于冷却中，剩余 {rem} 秒，跳过此轮")
                        send_tg(f"⏳ 冷却中 ({rem}s)", server_name, before_text)
                        # 冷却中，跳过本次续期，继续外层循环重试
                        continue

                    # 开始续期操作
                    log("🖱️ 正在寻找并点击 +90 分钟续期按钮...")
                    click_done = False

                    # === Step 1: Pro v10 深度诊断 ===
                    log("🔍 Pro v10: 深度诊断...")
                    diag = sb.execute_script("""
                        (function(){
                            var btn = document.querySelector('button.rt-btn-free');
                            if(!btn) return 'not-found';
                            var rect = btn.getBoundingClientRect();
                            return {
                                text: btn.innerText,
                                visible: (btn.offsetParent !== null),
                                disabled: btn.disabled,
                                rect: rect
                            };
                        })()
                    """)
                    log(f"   🔬 诊断结果: {diag}")
                    screenshot(sb, "button-diagnosis-v10")

                    # === Step 2: Livewire HTTP API 直接调用 ===
                    try:
                        log("📍 策略1: Livewire HTTP API 直接调用 extend...")
                        component_id = find_component_id_by_selector(sb, 'button.rt-btn-free')
                        if component_id:
                            result = sb.execute_script("""
                                (function() {{
                                    if (!window.Livewire) return 'no-lw';
                                    var comps = window.Livewire.all();
                                    var targetComp = null;
                                    for (var c = 0; c < comps.length; c++) {{
                                        if (comps[c].id === '{component_id}') {{
                                            targetComp = comps[c];
                                            break;
                                        }}
                                    }}
                                    if (!targetComp) return 'no-target-component';
                                    try {{
                                        targetComp.call('extend');
                                        return 'called-via-call';
                                    }} catch(e) {{
                                        return 'call-failed:' + e.message;
                                    }}
                                }})();
                            """).format(component_id)
                            log(f"   🎯 Livewire call 结果: {result}")

                            if 'called' in str(result):
                                click_done = True
                                time.sleep(2)

                                reqs = sb.execute_script("return (window.__reqs || []).length;")
                                log(f"   📡 Livewire requests captured: {reqs}")

                                if reqs > 0:
                                    log("   ✅ 确认 Livewire POST 请求已发出！")
                                    screenshot(sb, "livewire-request-captured")
                        else:
                            log("   ⚠️ 未找到匹配的 Livewire 组件，尝试通用方法...")
                            # Fallback: 遍历所有组件试 extend
                            lw_result = sb.execute_script("""
                                if (!window.Livewire) return 'no-lw';
                                var comps = window.Livewire.all();
                                for (var c = 0; c < comps.length; c++) {
                                    try {
                                        comps[c].call('extend');
                                        return 'called-generic-' + c;
                                    } catch(e) {}
                                }
                                return 'no-match-any';
                            """)
                            log(f"   🎯 通用 Livewire 结果: {lw_result}")
                            if 'called' in str(lw_result):
                                click_done = True
                                time.sleep(2)

                    except Exception as e:
                        log(f"   ⚠️ 策略1失败: {e}")

                    # === Step 3: dispatch livewire:submit 事件 ===
                    if not click_done:
                        try:
                            log("📍 策略2: dispatch livewire:submit 事件...")
                            elem = sb.find_element(By.CSS_SELECTOR, 'button.rt-btn-free', timeout=5)
                            sb.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
                            result = sb.execute_script("""
                                var btn = arguments[0];
                                btn.style.pointerEvents = 'auto';
                                btn.removeAttribute('disabled');
                                ['mousedown','mouseup','click'].forEach(function(type){
                                    btn.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window}));
                                });
                                return 'events-dispatched';
                            """, elem)
                            log(f"   🎯 事件分发结果: {result}")
                            click_done = True
                            time.sleep(1)
                        except Exception as e:
                            log(f"   ⚠️ 策略2失败: {e}")

                    # === Step 4: 纯 JS .click() 兜底 ===
                    if not click_done:
                        try:
                            log("📍 策略3: 纯 JS .click() 兜底...")
                            js_result = sb.execute_script("""
                                var btns = document.querySelectorAll('button');
                                for (var i = 0; i < btns.length; i++) {
                                    if ((btns[i].textContent || '').indexOf('90') !== -1) {
                                        btns[i].scrollIntoView({block: 'center'});
                                        btns[i].removeAttribute('disabled');
                                        btns[i].style.cssText += '; pointer-events:auto !important;';
                                        btns[i].click();
                                        return 'native-clicked:' + (btns[i].textContent || '').trim();
                                    }
                                }
                                return 'not-found';
                            """)
                            log(f"🎯 兜底 click 结果: {js_result}")
                            if 'native-clicked' in js_result:
                                click_done = True
                        except Exception as e:
                            log(f"⚠️ 策略3失败: {e}")

                    # === Pro v10 二次点击重试 ===
                    if not click_done:
                        log("⚠️ 第一次点击失败，Pro重新尝试")
                        screenshot(sb, "click-failed")
                        time.sleep(5)
                        sb.refresh()
                        time.sleep(10)
                        js_result = sb.execute_script("""
                        let btns=document.querySelectorAll('button');
                        for(let b of btns){
                            if(b.innerText.includes('90')){
                                b.scrollIntoView({block:'center'});
                                b.click();
                                return b.innerText;
                            }
                        }
                        return 'none';
                        """)
                        log(f"🔁 Pro二次点击: {js_result}")
                        if js_result != "none":
                            click_done = True

                    if not click_done:
                        log("❌ 所有点击策略均失败")
                        screenshot(sb, "点击全部失败")
                        send_tg("❌ 无法点击续期按钮", server_name, before_text)
                        continue

                    # === Pro v10 增强: 实时监控页面响应与验证码 ===
                    log("⏳ 正在监控页面响应与 Turnstile 验证碼 (最多 20 秒)...")

                    def check_turnstile_present():
                        try:
                            return bool(sb.execute_script("""
                                return (function() {
                                    return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                        || !!document.querySelector('.cf-turnstile')
                                        || !!document.querySelector('[class*="turnstile-"]')
                                        || !!document.querySelector('[data-testid="turnstile-widget"]')
                                        || !!document.querySelector('[aria-label="Security verification"]')
                                        || (document.body && document.body.innerText.includes("Verify you're human"));
                                })();
                            """))
                        except Exception:
                            return False

                    responded = False
                    turnstile_handled_count = 0
                    for wi in range(20):
                        time.sleep(1)

                        # 1. 优先检查并处理 Turnstile
                        if check_turnstile_present():
                            if turnstile_handled_count % 5 == 0:
                                log(f"🛡️ [第 {wi+1} 秒] 实时检测到 Turnstile, 调用 handle_turnstile (UC 模式原生点击)...")
                                screenshot(sb, f"turnstile-detected-{turnstile_handled_count}")
                            
                            try:
                                # 优先使用 SeleniumBase 的原生 UC 验证码处理
                                sb.uc_gui_click_captcha()
                                time.sleep(2)
                            except Exception as e:
                                log(f"⚠️ UC 原生点击异常: {e}")
                                # 兜底: 使用 xdotool 进行底层系统点击 (绕过 CDP 检测)
                                try:
                                    cf_iframes = sb.find_elements('iframe[src*="challenges.cloudflare.com"]') or \
                                                 sb.find_elements('iframe[src*="cloudflare"]')
                                    if cf_iframes:
                                        iframe = cf_iframes[0]
                                        rect = sb.execute_script(
                                            "(function() { var el = arguments[0]; var r = el.getBoundingClientRect(); "
                                            "return {x: r.x, y: r.y, w: r.width, h: r.height}; })();",
                                            iframe
                                        )
                                        if rect and rect.get('w', 0) > 0:
                                            # 点击 checkbox 区域 (iframe 左侧 30px)
                                            click_x = int(rect['x'] + 30)
                                            click_y = int(rect['y'] + rect['h'] / 2)
                                            subprocess.run(["xdotool", "mousemove", str(click_x), str(click_y)], check=False)
                                            time.sleep(0.2)
                                            subprocess.run(["xdotool", "click", "1"], check=False)
                                except Exception: pass
                            
                            turnstile_handled_count += 1
                            continue

                        # 2. 检查时间是否增加
                        page_after = sb.execute_script("(function(){ return document.body?document.body.innerText:''; })()")
                        match_new = re.search(r'(\d+:){2}\d+', page_after)
                        if match_new:
                            new_secs = parse_countdown_seconds(match_new.group(0))
                            if new_secs > before_secs + 30:
                                log(f"✅ 页面已响应！新时间: {match_new.group(0)}")
                                responded = True
                                break

                    if not responded:
                        log("ℹ️ 页面在 20 秒内未检测到时间显著变化")

                    screenshot(sb, "after-click-status-check")

                    # === Pro v8: 点击后主动调用 Livewire ===
                    method = analyze_livewire(sb)
                    if method:
                        log(f"🎯 Pro发现续期方法: {method}")
                        # 尝试找到组件ID
                        comp_id = find_component_id_by_selector(sb, 'button.rt-btn-free')
                        if comp_id:
                            call_livewire_directly(sb, comp_id, method)
                        else:
                            # 通用调用
                            sb.execute_script("""
                                if(window.Livewire){{
                                    let comps=Livewire.all();
                                    if(comps.length>0){{
                                        comps[0].call("{method}");
                                        return "called";
                                    }}
                                }}
                                return "no";
                            """).format(method)

                    # === 进入广告观看流程 ===
                    live_text, res = wait_ad_flow(sb, before_secs, AD_WAIT_SEC)

                    # === Pro 最终确认 ===
                    ok, verify_text = verify_extend_success(sb, before_secs)

                    if ok:
                        log(f"✅ Pro续期成功: {verify_text}")
                        send_tg("✅ Pro续期成功", server_name, verify_text)
                        # 【关键修复】续期成功后，标记并退出重试循环
                        account_finished = True
                        break
                    else:
                        log(f"❌ Pro续期失败: {verify_text}")
                        send_tg("❌ Pro续期失败", server_name, verify_text)

                        # Pro v7: 失败自动重试
                        if RETRY_AFTER_FAIL:
                            log("♻️ Pro模式: 失败自动重试...")
                            recover_page(sb, server_url)
                            time.sleep(5)
                            continue  # 重新执行内部 browser_attempt 流程

                # 如果账号处理完成，跳出浏览器重试循环
                if account_finished:
                    break

            except RuntimeError as e:
                log(f"❌ 浏览器进程崩溃: {e}")
                if browser_attempt < max_browser_retries - 1:
                    log(f"⏳ 等待 {browser_retry_delay} 秒后重新启动浏览器...")
                    time.sleep(browser_retry_delay)
                    continue
                else:
                    log("❌ 浏览器连续崩溃")
                    send_tg("❌ 浏览器连续崩溃", server_name)
                    break

            except Exception as e:
                log(f"❌ 服务器 '{server_name}' 执行过程中发生异常: {e}\n{traceback.format_exc()}")
                try:
                    screenshot(sb, "错误截图")
                except: pass
                send_tg(f"❌ 执行异常: {e}", server_name)
                break


def wait_ad_flow(sb, before_secs, max_wait=AD_WAIT_SEC):
    """等待广告流程完成，监控续期结果 (Pro增强版)"""
    result = {'extend_seen': False, 'reward_ready': False, 'ad_seen': False, 'live_text': '', 'live_secs': 0}
    log(f"🎬 进入广告观看流程 (最长 {max_wait}秒, 期间不刷新页面)...")

    # === 【调试】广告 DOM 检测 ===
    try:
        log("===== 广告DOM检测 =====")

        # 检测 iframe
        iframes = sb.execute_script("""
            (function() {
                var ifs = document.querySelectorAll('iframe');
                var info = [];
                for (var i = 0; i < ifs.length; i++) {
                    info.push({
                        index: i,
                        src: ifs[i].src || '(no src)',
                        width: ifs[i].offsetWidth,
                        height: ifs[i].offsetHeight,
                        visible: (ifs[i].offsetParent !== null)
                    });
                }
                return JSON.stringify(info);
            })();
        """)
        log(f"📺 iframe详情: {iframes}")

        # 检测页面文本
        body_text = sb.execute_script("(function(){ return document.body?document.body.innerText.substring(0,1000):''; })()")
        log(f"📄 页面文本前1000字符:\n{body_text[:500]}...")

        # 检测包含 "ad" 或 "Watching" 的元素
        ad_elements = sb.execute_script("""
            (function() {
                var all = document.querySelectorAll('*');
                var ads = [];
                for (var i = 0; i < all.length; i++) {
                    var txt = (all[i].textContent || '').toLowerCase();
                    if ((txt.indexOf('ad') !== -1 || txt.indexOf('watching') !== -1) && all[i].offsetParent !== null) {
                        ads.push({
                            tag: all[i].tagName,
                            cls: all[i].className || '',
                            text: (all[i].textContent || '').substring(0,100).trim()
                        });
                    }
                }
                return JSON.stringify(ads.slice(0, 10));
            })();
        """)
        log(f"🔍 广告相关元素: {ad_elements}")

    except Exception as e:
        log(f"⚠️ 广告DOM检测失败: {e}")

    # === 截图：广告流程开始时 ===
    screenshot(sb, "ad-flow-start")

    t0 = time.time()
    clicked_again = False
    alpine_logged = 0
    ad_first_seen = None

    while time.time() - t0 < max_wait:
        elapsed = time.time() - t0

        # === Pro广告卡死检测 ===
        # Log warning only - do NOT break the ad flow; Livewire rendering can cause false positives
        if int(elapsed) >= 5 and int(elapsed) % 20 == 0:
            try:
                if detect_page_stuck(sb):
                    log("⚠️ 检测到广告页面可能卡死 (忽略，继续等待)")
                    screenshot(sb, "ad-stuck-partial")
            except Exception as e:
                log(f"广告检测异常: {e}")

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

            # 【调试】广告开始5秒后截图
            time.sleep(5)
            screenshot(sb, "ad-playing-5s")

        if result['reward_ready'] and not clicked_again:
            clicked_again = True
            log("🎁 广告奖励已就绪！等待 5 分钟冷却结束...")

            # 【关键修复】只需等待冷却结束，无需二次点击
            # 系统会在冷却完成后自动续期
            for ci in range(300):  # 最多等 5 分钟 (300 * 10秒)
                cooldown_info = check_button_cooldown(sb)
                if cooldown_info and cooldown_info.get('cooldown'):
                    remaining = cooldown_info.get('remaining', '?')
                    log(f"   ⏳ 按钮冷却中，剩余 {remaining}秒")
                    time.sleep(10)
                    continue
                else:
                    log("✅ 按钮冷却已结束，等待续期生效...")
                    break

            # 再等 30 秒让系统完成续期
            log("⏳ 等待续期最终处理...")
            time.sleep(30)
            break

        time.sleep(2)

    return result.get('live_text', ''), result


if __name__ == "__main__":
    main()
