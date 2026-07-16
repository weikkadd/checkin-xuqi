以下是为你修复并补全的 `renew.py` 完整代码。

我已经将末尾截断的 `try` 块补全，并完善了 `wait_ad_flow` 函数的结尾逻辑。**注意：由于你之前的代码在这里截断了，如果你原本还有后续的执行主函数（如 `if __name__ == '__main__':`），请直接将它们拼接到此代码的末尾即可。**

```python
#!/usr/bin/env python3
"""
gaming4free 自动续期脚本 v5
- 核心: 识别并走完「看广告得时长」流程 (adLoading → adRewardReady → 必要时再点 +90 → extend)
- 核心: 按 Livewire 方法名识别真实续期调用 (轮询 $refresh 不再误报为「疑似续期请求」)
- 修复: 点击后不再立刻重载页面 (会打断广告流程); 不再乱点 Confirm/OK (会误杀广告弹窗)
- 修复: 「时间异常减少」误报 — 两次读取间的自然流逝不等于异常
- 增加: Alpine 组件状态实时观测 + 完整按钮 HTML dump + 广告元素检测
- 保留: uc_click 真实点击 / Turnstile 处理 / fetch+XHR 请求监听
- 更新: 实现方案 A — 点击前轮询等待按钮文本变为 "watch ad · +90 min"，避免误触验证码
"""

import os, time, random, urllib.request, urllib.parse, re
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

TARGET_SECONDS = 48 * 3600
ADD_SECONDS = 90 * 60
COOLDOWN_SEC = 120
MAX_ROUNDS = 5
AD_WAIT_SEC = 100
SCREENSHOT_DIR = "/tmp/g4f-debug"

# ================== 工具函数 ==================
def now_str():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print(f"{msg}", flush=True)

def screenshot(sb, name):
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        path = f"{SCREENSHOT_DIR}/{name}.png"
        sb.save_screenshot(path)
        log(f"[截图] {path}")
    except:
        pass

def send_tg(result, server_name="", expiry=""):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    msg = (
        f"🎮Game4Free 续期通知\n"
        f"⏰运行时间: {now_str()}\n"
        f"🖥️服务器: {server_name}\n"
    )
    if expiry:
        msg += f"🔢剩余时间: {expiry}\n"
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
                text = sb.execute_script(
                    "(function() { var el = document.querySelector('" + sel + "'); "
                    "return el ? el.textContent.trim() : ''; })();"
                )
                if text and len(text) < 30:
                    secs = parse_countdown_seconds(text)
                    if secs > 0: return text, secs
            except: continue
        page_text = sb.execute_script(
            "(function() { return document.body ? document.body.innerText : ''; })();"
        )
        if page_text:
            match = re.search(r'(\d{1,2}:\d{2}:\d{2})', page_text)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
            match = re.search(r'(\d+h\s*\d+m)', page_text, re.I)
            if match: return match.group(1), parse_countdown_seconds(match.group(1))
    except: pass
    return "", 0

def close_modals(sb):
    """关闭遮挡按钮的弹窗"""
    try:
        close_selectors = [
            'button:contains("Maybe later")',
            'button:contains("×")',
            '.modal-close',
            'button:contains("Enjoy ad-free")',
            '[aria-label="Close"]',
        ]
        for sel in close_selectors:
            try:
                is_modal = sb.execute_script(
                    "(function() { var el = document.querySelector('" + sel + "'); "
                    "if (!el) return false; var p = el.parentElement; "
                    "while(p) { if (p.className && (p.className.indexOf('modal') !== -1 "
                    "|| p.className.indexOf('dialog') !== -1 || p.tagName === 'DIALOG')) return true; "
                    "p = p.parentElement; } return false; })();"
                )
                if is_modal:
                    sb.click(sel)
                    log(f"🛡️ 已关闭弹窗: {sel}")
                    time.sleep(1)
            except: continue
    except: pass

def clear_overlays(sb):
    """点击前移除可能遮挡按钮的 modal/overlay 残留"""
    try:
        removed = sb.execute_script("""
        (function() {
            var n = 0;
            document.querySelectorAll(
                '.modal-backdrop, .modal.show, [x-show="true"][x-transition], ' +
                '.fixed.inset-0.bg-black, .v-overlay, .modal-open'
            ).forEach(function(el){
                var txt = (el.innerText || '').trim();
                var rect = el.getBoundingClientRect();
                if (txt.length === 0 || (rect.width > window.innerWidth * 0.8
                    && rect.height > window.innerHeight * 0.8)) {
                    el.remove();
                    n++;
                }
            });
            return n;
        })();
        """)
        if removed:
            log(f"🧹 清除 {removed} 个遮罩残留")
            time.sleep(0.5)
    except Exception:
        pass

def check_button_cooldown(sb):
    """检查 +90 按钮是否处于冷却"""
    cooldown_check = """
    (function() {
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var text = btns[i].innerText || '';
            if (text.indexOf('90') !== -1) {
                var disabled = btns[i].disabled || btns[i].getAttribute('aria-disabled') === 'true';
                var classes = btns[i].className || '';
                var isCooldown = classes.indexOf('disabled') !== -1
                    || classes.indexOf('cursor-not-allowed') !== -1 || disabled;
                var waitMatch = text.match(/Wait\\s*(\\d+)/i) || text.match(/(\\d+)\\s*s/);
                if (waitMatch) {
                    return {cooldown: true, remaining: parseInt(waitMatch[1]), text: text.trim()};
                }
                if (isCooldown) {
                    return {cooldown: true, disabled: true, text: text.trim()};
                }
                return {cooldown: false, text: text.trim(), html: btns[i].outerHTML.substring(0, 200)};
            }
        }
        return null;
    })();
    """
    try:
        return sb.execute_script(cooldown_check)
    except:
        return None

def handle_turnstile(sb, max_retries=3):
    """处理 Cloudflare Turnstile 验证"""
    for attempt in range(max_retries):
        try:
            cf_iframes = sb.find_elements('iframe[src*="cloudflare"]') or \
                         sb.find_elements('iframe[src*="turnstile"]') or \
                         sb.find_elements('iframe[title*="challenge"]')
            if cf_iframes:
                log(f"🛡️ 检测到 Turnstile (尝试 {attempt+1}/{max_retries})")
                screenshot(sb, f"turnstile-{attempt}")
                try:
                    sb.uc_gui_click_captcha()
                    log("✅ uc_gui_click_captcha 已执行")
                    time.sleep(5)
                    return True
                except Exception as e:
                    log(f"⚠️ uc_gui_click_captcha 失败: {e}")
                    try:
                        sb.switch_to_frame('iframe[src*="cloudflare"]')
                        sb.click('input[type="checkbox"]')
                        sb.switch_to_default_content()
                        log("✅ 手动点击 checkbox")
                        time.sleep(5)
                        return True
                    except:
                        sb.switch_to_default_content()
        except:
            pass
        time.sleep(2)
    return False

# ================== v5: 广告流程处理 ==================
POLLING_METHODS = ('$refresh', 'refresh', 'poll', '$poll')

def read_alpine_state(sb):
    """读取 +90 按钮所属 Alpine 组件的实时状态"""
    js = """
    (function() {
        var btn = null;
        var all = document.querySelectorAll('button');
        for (var i = 0; i < all.length; i++) {
            if ((all[i].innerText || '').indexOf('90') !== -1) { btn = all[i]; break; }
        }
        if (!btn) return null;
        var st = {cls: btn.className || '', disabledAttr: !!btn.disabled, hasAlpine: false};
        var root = btn.closest('[x-data]') || btn;
        var d = null;
        try { if (window.Alpine && Alpine.$data) d = Alpine.$data(root); } catch(e) {}
        try { if (!d && root.__x && root.__x.$data) d = root.__x.$data; } catch(e) {}
        if (d) {
            st.hasAlpine = true;
            for (var k in d) {
                try {
                    var v = d[k];
                    var tv = typeof v;
                    if ((tv === 'boolean' || tv === 'number' || tv === 'string') && ('' + v).length < 60) {
                        st[k] = v;
                    }
                } catch(e) {}
            }
        }
        return st;
    })();
    """
    try:
        return sb.execute_script(js)
    except Exception:
        return None

def detect_ad(sb):
    """检测页面上正在展示的广告"""
    js = """
    (function() {
        var vids = document.querySelectorAll('video');
        for (var i = 0; i < vids.length; i++) {
            if (vids[i].offsetParent !== null) {
                return 'video(dur=' + (vids[i].duration || '?') + ',t=' + (vids[i].currentTime || 0).toFixed(0) + ',paused=' + vids[i].paused + ')';
            }
        }
        var ifs = document.querySelectorAll('iframe');
        for (var j = 0; j < ifs.length; j++) {
            var s = ((ifs[j].src || '') + ' ' + (ifs[j].id || '') + ' ' + (ifs[j].name || ''));
            if (/ads|doubleclick|googlesyndication|adnxs|pubmatic|reward|vast/i.test(s) && ifs[j].offsetParent !== null) {
                return 'iframe:' + (ifs[j].src || '').substring(0, 90);
            }
        }
        var modals = document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="Modal"]');
        for (var k = 0; k < modals.length; k++) {
            var el = modals[k];
            if (el.offsetParent !== null) {
                var t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                if (/ad|广告|reward|watch/i.test(t) && t.length > 0 && t.length < 200) {
                    return 'modal:' + t.substring(0, 80);
                }
            }
        }
        return '';
    })();
    """
    try:
        return sb.execute_script(js) or ''
    except Exception:
        return ''

def try_ad_controls(sb, ad_elapsed):
    """广告展示中的保守操作"""
    try:
        r = sb.execute_script("""
        (function() {
            var kws = ['claim', 'collect', '领取', 'get reward', 'claim reward', '获取奖励'];
            var els = document.querySelectorAll('button, a, [role="button"]');
            for (var i = 0; i < els.length; i++) {
                var t = (els[i].innerText || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                if (t.length === 0 || t.length > 30) continue;
                if (els[i].offsetParent === null) continue;
                for (var k = 0; k < kws.length; k++) {
                    if (t.indexOf(kws[k]) !== -1) { els[i].click(); return 'claim:' + t; }
                }
            }
            return '';
        })();
        """)
        if r:
            log(f"🎁 点击广告奖励按钮: {r}")
            return
    except Exception:
        pass
    if ad_elapsed > 20:
        try:
            r2 = sb.execute_script("""
            (function() {
                var els = document.querySelectorAll('[aria-label="Close"], [aria-label="close"], button[class*="close"], [class*="modal"] button');
                for (var i = 0; i < els.length; i++) {
                    var t = (els[i].innerText || '').trim();
                    if (els[i].offsetParent === null) continue;
                    if (!(t === '×' || t === '✕' || t === 'x' || t === 'X' || t === ''
                          || /close/i.test(els[i].getAttribute('aria-label') || ''))) continue;
                    var p = els[i];
                    while (p) {
                        if (p.getAttribute && (p.getAttribute('role') === 'dialog' || /modal|dialog/i.test(p.className || ''))) {
                            els[i].click();
                            return 'closed ad modal';
                        }
                        p = p.parentElement;
                    }
                }
                return '';
            })();
            """)
            if r2:
                log(f"🧹 广告已超 20s, 尝试关闭: {r2}")
        except Exception:
            pass

def wait_ad_flow(sb, before_secs, max_wait=AD_WAIT_SEC):
    """v5 核心: 点击 +90 后等广告流程走完, 并捕获真实的续期调用。"""
    result = {'extend_seen': False, 'reward_ready': False, 'ad_seen': False,
              'live_text': '', 'live_secs': 0}
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
        except Exception:
            calls = []
        real_methods = []
        for c in calls:
            for m in (c.get('methods') or []):
                if m not in POLLING_METHODS and m not in real_methods:
                    real_methods.append(m)
        if real_methods:
            log(f"✅ 捕获真实 Livewire 调用: method={real_methods}")
            result['extend_seen'] = True
            screenshot(sb
