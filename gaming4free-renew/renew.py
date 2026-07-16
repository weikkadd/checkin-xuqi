#!/usr/bin/env python3
"""
gaming4free 自动续期脚本 v4
- 修复: 点击 +90 后立即处理 Turnstile 验证
- 修复: 广告关键词误匹配
- 增加: 点击后网络请求监听
- 增加: 每步截图调试
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
# 修复 #5: 原值 MAX_ROUNDS=10 + COOLDOWN=300s 单账号约 50 分钟, 超过 Actions 30 分钟限制
# 改为 5 轮 × 120s ≈ 10 分钟, 配合 timeout 60 分钟可稳定跑完
COOLDOWN_SEC = 120
MAX_ROUNDS = 5
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
    """点击前移除可能遮挡按钮的 modal/overlay 残留 (修复 #6)

    上一轮失败后页面常残留半透明遮罩/backdrop, 导致真实点击落在遮罩上而非按钮。
    这里只移除明确的遮罩层, 不碰功能元素。
    """
    try:
        removed = sb.execute_script("""
        (function() {
            var n = 0;
            // Tailwind/Livewire 常见遮罩: modal backdrop, fixed 全屏遮罩
            document.querySelectorAll(
                '.modal-backdrop, .modal.show, [x-show="true"][x-transition], ' +
                '.fixed.inset-0.bg-black, .v-overlay, .modal-open'
            ).forEach(function(el){
                // 只删确实是遮罩的 (无文字内容 或 全屏 fixed)
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
            # 方法1: uc_gui_click_captcha (最可靠)
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
                    # 方法2: 直接点击 iframe 内 checkbox
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

def dump_buttons(sb):
    """调试: 打印页面上所有含 '90' 的按钮的 outerHTML 和 wire:click 属性"""
    try:
        info = sb.execute_script("""
        (function() {
            var out = [];
            var all = document.querySelectorAll('button, [role="button"], a');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var t = (el.innerText || el.textContent || "").replace(/\\s+/g, ' ').trim();
                if (t.indexOf('90') !== -1 || /90/.test(el.getAttribute('wire:click') || '')) {
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        text: t.substring(0, 40),
                        wc: el.getAttribute('wire:click') || '',
                        disabled: el.disabled || (el.getAttribute('aria-disabled') === 'true'),
                        html: el.outerHTML.substring(0, 160)
                    });
                }
            }
            return out;
        })();
        """)
        if info:
            log(f"🔎 [调试] 含 90 的按钮共 {len(info)} 个:")
            for b in info:
                log(f"    <{b.get('tag')}> wc='{b.get('wc')}' disabled={b.get('disabled')} text='{b.get('text')}'")
        else:
            log("🔎 [调试] 未找到任何含 90 的按钮")
        return info or []
    except Exception as e:
        log(f"⚠️ dump_buttons 异常: {e}")
        return []


def click_plus_90(sb):
    """点击 +90 min 按钮 — 优先按 wire:click 属性定位 (不依赖文字子串)"""
    close_modals(sb)
    # 每轮点击前清理可能遮挡的 modal/overlay 残留 (修复 #6)
    clear_overlays(sb)

    # 调试: 先 dump 出真实按钮结构 (修复 #1)
    btn_info = dump_buttons(sb)

    # 检查 cooldown
    btn_status = check_button_cooldown(sb)
    if btn_status and btn_status.get('cooldown'):
        remaining = btn_status.get('remaining', '?')
        log(f"⏳ 按钮冷却中: {btn_status.get('text','')} (剩余 {remaining}s)")
        return False
    if btn_status:
        log(f"📋 按钮状态: {btn_status.get('text','')}")

    clicked = False

    # 1. ★ 优先: 按 wire:click 属性精确定位 (修复 #1 核心)
    #    不再依赖文字子串 "90 min" (会被 span/strong 碎片/换行/图标打断)
    if not clicked:
        try:
            result = sb.execute_script("""
            (function() {
                var cands = document.querySelectorAll('[wire\\\\:click]');
                for (var i = 0; i < cands.length; i++) {
                    var wc = cands[i].getAttribute('wire:click') || '';
                    if (/90/.test(wc) && !cands[i].disabled
                        && cands[i].getAttribute('aria-disabled') !== 'true') {
                        cands[i].scrollIntoView({block: 'center', behavior: 'instant'});
                        try { cands[i].focus(); } catch(e) {}
                        try { cands[i].click(); } catch(e) {}
                        return 'wc-clicked: ' + wc + ' on <' + cands[i].tagName.toLowerCase() + '>';
                    }
                }
                return false;
            })();
            """)
            if result:
                log(f"🎯 [策略1] wire:click 定位点击: {result}")
                clicked = True
        except Exception as e:
            log(f"⚠️ [策略1] wire:click 点击异常: {e}")

    # 2. 备用: 含 90 的可点击元素, 用原生 element.click() (isTrusted=true)
    if not clicked:
        try:
            result = sb.execute_script("""
            (function() {
                var all = document.querySelectorAll('button, [role="button"], a');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var t = (el.innerText || el.textContent || "").replace(/\\s+/g, ' ').trim();
                    // 宽松匹配: 文字里含 90, 且文本短, 且未禁用
                    if (t.length <= 30 && /90/.test(t) && !el.disabled
                        && el.getAttribute('aria-disabled') !== 'true') {
                        el.scrollIntoView({block: 'center', behavior: 'instant'});
                        try { el.focus(); } catch(e) {}
                        try { el.click(); } catch(e) {}
                        return 'text-clicked: ' + t + ' on <' + el.tagName.toLowerCase() + '>';
                    }
                }
                return false;
            })();
            """)
            if result:
                log(f"🚀 [策略2] 含90元素原生 click(): {result}")
                clicked = True
        except Exception as e:
            log(f"⚠️ [策略2] 异常: {e}")

    # 3. 检查广告按钮 (Watch Ad 等) — 广告流程可能在前置
    if not clicked:
        log("🔍 [策略3] 检查广告按钮...")
        ad_keywords = ['Watch Ad', 'Play Ad', 'Claim Reward', 'Get Free Time', 'Earn Time']
        for kw in ad_keywords:
            try:
                ad_result = sb.execute_script(
                    '(function() { var btns = document.querySelectorAll("button, a, [role=\\"button\\"]"); '
                    'for (var i = 0; i < btns.length; i++) { var t = (btns[i].innerText || "").trim(); '
                    'if (t.toLowerCase().indexOf("' + kw.lower() + '") !== -1 && t.length < 30) { '
                    'btns[i].scrollIntoView({block: "center"}); try{btns[i].click();}catch(e){} return "ad:" + t; } } '
                    'return false; })();'
                )
                if ad_result:
                    log(f"🎬 [策略3] 广告按钮: {ad_result}")
                    time.sleep(15)
                    # 广告后再找含 90 的按钮
                    result2 = sb.execute_script(
                        '(function() { var btns = document.querySelectorAll("button, [role=\\"button\\"]"); '
                        'for (var i = 0; i < btns.length; i++) { var t = (btns[i].innerText||"").replace(/\\s+/g," ").trim(); '
                        'if (/90/.test(t) && t.length < 30 && !btns[i].disabled) { '
                        'btns[i].scrollIntoView({block:"center"}); try{btns[i].click();}catch(e){} return "clicked:"+t; } } '
                        'return false; })();'
                    )
                    if result2:
                        log(f"🚀 [策略3] 广告后点击 +90: {result2}")
                        clicked = True
                        break
            except:
                continue

    # 4. 最后兜底: SeleniumBase WebDriver 真实点击 (isTrusted=true)
    #    注意: 不用 contains(@wire:click,...) — XPath 1.0 会把 'wire:' 当命名空间前缀报错
    #    wire:click 场景已由策略1的 CSS 选择器覆盖
    if not clicked:
        xpaths = [
            "//button[contains(., '90 min') and not(contains(., 'Wait'))]",
            "//button[contains(., '+ 90') and not(contains(., 'Wait'))]",
            "//*[contains(text(), '90')]/ancestor::button[not(contains(., 'Wait'))]",
        ]
        for xpath in xpaths:
            try:
                if sb.is_element_visible(xpath):
                    sb.scroll_to(xpath)
                    time.sleep(0.5)
                    screenshot(sb, "before-click")
                    sb.click(xpath)
                    log(f"✅ [策略4] WebDriver 兜底点击: {xpath}")
                    clicked = True
                    break
            except:
                continue

    if not clicked:
        log("❌ 所有点击策略失败")
        screenshot(sb, "click-fail")
        return False

    # 点击后统一处理 Turnstile
    time.sleep(2)
    screenshot(sb, "after-click")
    handle_turnstile(sb)
    time.sleep(5)
    return True

def handle_confirm(sb):
    """处理确认按钮"""
    time.sleep(2)
    handle_turnstile(sb)
    confirm_keywords = ['確認', '確定', 'OK', 'Confirm', '确认', 'Yes', 'Continue', 'Verify']
    for kw in confirm_keywords:
        try:
            sb.execute_script(
                '(function() { var btns = document.querySelectorAll("button, a"); '
                'for (var i = 0; i < btns.length; i++) { '
                'if (btns[i].innerText.indexOf("' + kw + '") !== -1) { '
                'btns[i].click(); return true; } } return false; })();'
            )
        except: continue

def renew_account(sb, server_name, renew_url):
    log(f"\n🎮 开始续期: {server_name}")
    parts = renew_url.rstrip('/').split('/')
    slug = None
    for part in reversed(parts):
        if part and part.lower() not in ['console', 'settings', 'server', 'servers', 'vote']:
            if len(part) >= 4:
                slug = part
                break
    if not slug:
        slug = parts[-1] if parts else ''
    console_url = f"https://control.gaming4free.net/server/{slug}/console"
    log(f"🔗 打开: {console_url}")

    # 修复 #4: reconnect 调大, 代理慢/Cloudflare 挑战时 6s 不够
    sb.uc_open_with_reconnect(console_url, reconnect_time=10)
    time.sleep(5)

    time_text, time_secs = get_remaining_time(sb)
    if time_text:
        log(f"📅 当前剩余: {time_text} ({time_secs // 3600}h {(time_secs % 3600) // 60}m)")

    if time_secs + ADD_SECONDS > TARGET_SECONDS:
        log(f"✅ 已达 48h 上限, 跳过")
        return time_text, time_secs, True

    # 检查按钮状态
    btn_status = check_button_cooldown(sb)
    if btn_status:
        log(f"📋 按钮信息: {btn_status.get('text','')} | cooldown={btn_status.get('cooldown')}")

    log("🔍 查找 +90 min 按钮...")
    # 监听网络请求: 记录点击后所有 XHR/fetch (修复 #2)
    # 不再只认 URL 含 'livewire' 的请求 — 站点可能用 /api/ 或其他端点
    try:
        sb.driver.execute_script("""
            (function() {
                window.__reqs = [];
                var isPost = function(method){ return (method||'').toUpperCase() === 'POST'; };
                var record = function(method, url, bodyHint) {
                    if (!url) return;
                    // 只记录 POST (续期是写操作) + 任何可疑端点, 过滤静态资源/轮询
                    if (/\\.(js|css|png|jpg|jpeg|gif|svg|woff|ico)(\\?|$)/i.test(url)) return;
                    if (/ipify|cloudflare|turnstile|recaptcha/i.test(url)) return;
                    window.__reqs.push({m: (method||'').toUpperCase(), u: String(url).substring(0, 120), b: bodyHint || ''});
                };
                var origFetch = window.fetch;
                window.fetch = function() {
                    var url = arguments[0], opt = arguments[1] || {};
                    try { record(opt.method || 'GET', (typeof url === 'string') ? url : (url && url.url), ''); } catch(e) {}
                    return origFetch.apply(this, arguments);
                };
                var origOpen = XMLHttpRequest.prototype.open;
                var origSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.open = function(method, url) {
                    this.__m = method; this.__u = url;
                    return origOpen.apply(this, arguments);
                };
                XMLHttpRequest.prototype.send = function(body) {
                    try {
                        var hint = '';
                        if (body && typeof body === 'string' && body.length < 200) hint = body.substring(0, 80);
                        record(this.__m, this.__u, hint);
                    } catch(e) {}
                    return origSend.apply(this, arguments);
                };
            })();
        """)
    except Exception as e:
        log(f"⚠️ 网络监听设置失败 (可忽略): {e}")

    if not click_plus_90(sb):
        screenshot(sb, f"fail_{server_name}")
        return time_text, time_secs, False

    # 检查点击后是否真的发出请求 (修复 #2: 看 POST / 含 livewire|api|update 的)
    time.sleep(3)
    try:
        reqs = sb.execute_script("(function() { return window.__reqs || []; })();") or []
        # 优先找 POST 且端点可疑的 (续期写操作)
        renew_re = re.compile(r'livewire|api|update|renew|time|add', re.I)
        renew_candidates = [r for r in reqs
                            if r.get('m') == 'POST'
                            and renew_re.search((r.get('u','') + ' ' + r.get('b','')))]
        if reqs:
            log(f"🌐 点击后共 {len(reqs)} 个请求, 其中 POST {len([r for r in reqs if r.get('m')=='POST'])} 个")
            # 调试: 打印所有 POST 帮助定位真实端点
            for r in reqs:
                if r.get('m') == 'POST':
                    log(f"    📤 POST {r.get('u')}  body={r.get('b')!r}")
        if renew_candidates:
            log(f"✅ 疑似续期请求: {renew_candidates[0].get('m')} {renew_candidates[0].get('u')}")
        else:
            log(f"⚠️ 未检测到续期类请求, 点击可能未生效 (检查上面 POST 列表确认真实端点)")
    except Exception as e:
        log(f"⚠️ 请求检查异常: {e}")

    # 处理确认/验证
    handle_confirm(sb)
    time.sleep(5)

    # 重新检查 Turnstile (可能延迟出现)
    handle_turnstile(sb)
    time.sleep(3)

    # 重新加载页面读取时间 (修复 #4: reconnect 调大 + 主动等计时器元素)
    try:
        sb.uc_open_with_reconnect(console_url, reconnect_time=10)
    except Exception as e:
        log(f"⚠️ 重新加载超时: {e}")
        time.sleep(5)

    # 修复 #4: 不要只 sleep 固定秒数, 主动等计时器元素出现 (最多 15s)
    timer_sels = ['[class*="timer"]', '[class*="remaining"]', '[class*="countdown"]', '#sd-timer']
    timer_ready = False
    for _ in range(15):
        for sel in timer_sels:
            try:
                txt = sb.execute_script(
                    "(function(){var el=document.querySelector('" + sel + "');"
                    "return el ? (el.textContent||'').trim() : '';})();"
                )
                if txt and len(txt) < 30 and parse_countdown_seconds(txt) > 0:
                    timer_ready = True
                    break
            except Exception:
                pass
        if timer_ready:
            break
        time.sleep(1)
    if not timer_ready:
        log("⚠️ 重载后计时器未就绪 (页面可能仍在加载/挑战)")

    new_text, new_secs = get_remaining_time(sb)

    # 修复 #3: 读不到时间时不要拿 0 去算 diff (那是假"时间异常减少")
    if not new_text:
        log(f"⚠️ 重载后读不到剩余时间文本 (旧={time_text}), 本轮判失败, 不误报")
        screenshot(sb, f"no-time-{server_name}")
        return time_text, time_secs, False

    time_diff = new_secs - time_secs

    if time_diff > 60:
        log(f"✅ 续期成功! {time_text} → {new_text} (+{time_diff//60}m {time_diff%60}s)")
        return new_text, new_secs, True
    elif time_diff >= -60:
        log(f"❌ 未生效! {time_text} → {new_text} (差 {time_diff}s)")
        screenshot(sb, f"no-effect-{server_name}")
        # 检查是否有错误提示
        try:
            error_text = sb.execute_script(
                '(function() { var el = document.querySelector(".alert, .error, [class*=\\"error\\"], '
                '[class*=\\"alert\\"]"); return el ? el.textContent.trim() : ""; })();'
            )
            if error_text:
                log(f"⚠️ 页面错误提示: {error_text}")
        except: pass
        return time_text, time_secs, False
    else:
        log(f"⚠️ 时间异常减少 ({time_text} → {new_text}, 差 {time_diff}s)")
        screenshot(sb, f"time-drop-{server_name}")
        return time_text, time_secs, False

def run_script():
    if not ACCOUNTS:
        log("❌ 未解析到任何账号")
        exit(1)

    sb_kwargs = {"uc": True, "test": True}
    if os.environ.get("IS_PROXY", "false").lower() == "true":
        proxy = os.environ.get("PROXY_URL") or os.environ.get("PROXY_SERVER")
        if proxy:
            sb_kwargs["proxy"] = proxy.strip()
            log(f"🔗 使用代理: {sb_kwargs['proxy']}")

    with SB(**sb_kwargs) as sb:
        log("🚀 浏览器就绪!")

        try:
            sb.open("https://api.ipify.org/?format=json")
            ip = sb.get_text('body')[:50]
            log(f"📍 出口IP: {ip}")
        except:
            log("⚠️ IP验证超时")

        if GF_COOKIE:
            log("🍪 注入 Cookie...")
            try:
                sb.open("https://control.gaming4free.net/")
                time.sleep(2)
                sb.execute_script(
                    '(function() { var cookieStr = ' + repr(GF_COOKIE) + '; '
                    'cookieStr.split(";").forEach(function(c) { '
                    'var parts = c.trim().split("="); '
                    'if (parts.length >= 2) { '
                    'document.cookie = parts[0].trim() + "=" + parts.slice(1).join("=") + "; path=/; domain=.gaming4free.net"; '
                    '} }); })();'
                )
                sb.open("https://control.gaming4free.net/")
                time.sleep(2)
                log("✅ Cookie 注入完成")
            except Exception as e:
                log(f"⚠️ Cookie 注入异常: {e}")

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

            if success_count > 0:
                log(f"\n🎉 [{server_name}] 共续期 {success_count} 次")
            else:
                log(f"\n❌ [{server_name}] 所有轮次均未成功")

if __name__ == "__main__":
    run_script()
