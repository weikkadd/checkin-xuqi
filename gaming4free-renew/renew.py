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
COOLDOWN_SEC = 300
MAX_ROUNDS = 10
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

def click_plus_90(sb):
    """点击 +90 min 按钮 — JS dispatchEvent 优先 (v3.1 验证可用)"""
    close_modals(sb)

    # 检查 cooldown
    btn_status = check_button_cooldown(sb)
    if btn_status and btn_status.get('cooldown'):
        remaining = btn_status.get('remaining', '?')
        log(f"⏳ 按钮冷却中: {btn_status.get('text','')} (剩余 {remaining}s)")
        return False

    if btn_status:
        log(f"📋 按钮状态: {btn_status.get('text','')}")

    # 1. ★ 优先: 原生 element.click() + WebDriver click 双重保险
    #    Livewire 3 / Filament 会检查 event.isTrusted
    #    - dispatchEvent(new MouseEvent) → isTrusted=false → 被忽略
    #    - element.click() → isTrusted=true → Livewire 接收
    #    所以必须用 el.click() 原生方法, 而非 dispatchEvent
    log("🚀 尝试原生 click() + dispatchEvent 组合点击...")
    js_real_click = """
    (function() {
        var targets = ["+ 90 min", "+90 min", "90 min"];
        var all = document.querySelectorAll('button, [role="button"], a, span');
        for (var i = 0; i < all.length; i++) {
            var el = all[i];
            var text = (el.innerText || el.textContent || "").trim();
            if (text.length > 30) continue;
            for (var j = 0; j < targets.length; j++) {
                if (text.indexOf(targets[j]) !== -1 && !el.disabled) {
                    el.scrollIntoView({block: 'center', behavior: 'instant'});
                    try { el.focus({preventScroll: false}); } catch(e) {}
                    var rect = el.getBoundingClientRect();
                    var x = rect.left + rect.width / 2;
                    var y = rect.top + rect.height / 2;
                    var opts = {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y};
                    // 先派发 mousedown/mouseup (合成, isTrusted=false, 但有些监听器需要)
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    // ★ 关键: 用原生 click() 方法, 触发 isTrusted=true 的 click 事件
                    try { el.click(); } catch(e) {}
                    // 同时再 dispatchEvent 一次兜底
                    el.dispatchEvent(new MouseEvent('click', opts));
                    // 如果文字在 span/strong 里, 也点父元素 button
                    if (el.tagName === 'SPAN' || el.tagName === 'STRONG') {
                        var p = el.parentElement;
                        if (p) {
                            try { p.click(); } catch(e) {}
                            p.dispatchEvent(new MouseEvent('click', opts));
                        }
                    }
                    return 'clicked:' + text + ' on <' + el.tagName.toLowerCase() + '>';
                }
            }
        }
        return false;
    })();
    """
    try:
        result = sb.execute_script(js_real_click)
        if result:
            log(f"🚀 原生 click(): {result}")
            screenshot(sb, "after-js-click")
            time.sleep(2)
            # 检查是否出现 Turnstile
            handle_turnstile(sb)
            time.sleep(5)  # 给 Livewire 请求时间
            # ★ 关键: 再用 WebDriver 真实点击一次 (双保险, isTrusted=true)
            try:
                xpath = "//button[contains(., '90 min') and not(contains(., 'Wait'))]"
                if sb.is_element_visible(xpath):
                    sb.scroll_to(xpath)
                    time.sleep(0.3)
                    sb.click(xpath)
                    log(f"🚀 WebDriver 二次点击: {xpath}")
                    time.sleep(3)
                    handle_turnstile(sb)
                    time.sleep(5)
            except Exception as e:
                log(f"⚠️ WebDriver 二次点击失败 (可忽略): {e}")
            return True
    except Exception as e:
        log(f"⚠️ JS 点击异常: {e}")

    # 2. 备用: 检查广告按钮 (Watch Ad 等)
    log("🔍 检查广告按钮...")
    ad_keywords = ['Watch Ad', 'Play Ad', 'Claim Reward', 'Get Free Time', 'Earn Time']
    for kw in ad_keywords:
        try:
            ad_script = (
                '(function() { var btns = document.querySelectorAll("button, a, [role=\\"button\\"]"); '
                'for (var i = 0; i < btns.length; i++) { var t = (btns[i].innerText || "").trim(); '
                'if (t.toLowerCase().indexOf("' + kw.lower() + '") !== -1 && t.length < 30) { '
                'btns[i].scrollIntoView({block: "center"}); btns[i].click(); return "ad:" + t; } } '
                'return false; })();'
            )
            ad_result = sb.execute_script(ad_script)
            if ad_result:
                log(f"🎬 广告按钮: {ad_result}")
                time.sleep(15)
                result2 = sb.execute_script(
                    '(function() { var btns = document.querySelectorAll("button"); '
                    'for (var i = 0; i < btns.length; i++) { var t = btns[i].innerText||""; '
                    'if (t.indexOf("90") !== -1) { btns[i].scrollIntoView({block:"center"}); '
                    'btns[i].click(); return "clicked:"+t.trim(); } } return false; })();'
                )
                if result2:
                    log(f"🚀 广告后点击 +90: {result2}")
                    time.sleep(2)
                    handle_turnstile(sb)
                    time.sleep(3)
                    return True
        except:
            continue

    # 3. 最后兜底: SeleniumBase 原生点击
    xpaths = [
        "//button[contains(text(), '+ 90 min')]",
        "//button[contains(., '+90 min')]",
        "//*[contains(text(), '+ 90 min')]/ancestor::button",
        "//button[contains(., '90 min')]",
    ]
    for xpath in xpaths:
        try:
            if sb.is_element_visible(xpath):
                sb.scroll_to(xpath)
                time.sleep(0.5)
                screenshot(sb, "before-click")
                sb.click(xpath)
                log(f"✅ 兜底点击: {xpath}")
                time.sleep(2)
                handle_turnstile(sb)
                time.sleep(5)
                screenshot(sb, "after-click")
                return True
        except:
            continue

    log("❌ 所有点击策略失败")
    screenshot(sb, "click-fail")
    return False

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

    sb.uc_open_with_reconnect(console_url, reconnect_time=6)
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
    # 监听网络请求, 确认点击是否真的发了 Livewire 请求
    livewire_requests = []
    try:
        sb.driver.execute_cdp_cmd("Network.enable", {})
        sb.driver.execute_script("""
            (function() {
                window.__lw_requests = [];
                var origFetch = window.fetch;
                window.fetch = function() {
                    var url = arguments[0];
                    if (typeof url === 'string' && url.indexOf('livewire') !== -1) {
                        window.__lw_requests.push(url);
                    }
                    return origFetch.apply(this, arguments);
                };
                var origXHR = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function(method, url) {
                    if (url && url.indexOf('livewire') !== -1) {
                        window.__lw_requests.push(method + ' ' + url);
                    }
                    return origXHR.apply(this, arguments);
                };
            })();
        """)
    except Exception as e:
        log(f"⚠️ 网络监听设置失败 (可忽略): {e}")

    if not click_plus_90(sb):
        screenshot(sb, f"fail_{server_name}")
        return time_text, time_secs, False

    # 检查是否真的发起了 Livewire 请求
    time.sleep(2)
    try:
        lw_reqs = sb.execute_script("(function() { return window.__lw_requests || []; })();") or []
        if lw_reqs:
            log(f"🌐 检测到 {len(lw_reqs)} 个 Livewire 请求: {lw_reqs[0]}")
        else:
            log(f"⚠️ 未检测到 Livewire 请求, 点击可能未生效")
    except: pass

    # 处理确认/验证
    handle_confirm(sb)
    time.sleep(5)

    # 重新检查 Turnstile (可能延迟出现)
    handle_turnstile(sb)
    time.sleep(3)

    # 重新加载页面读取时间
    try:
        sb.uc_open_with_reconnect(console_url, reconnect_time=6)
        time.sleep(3)
    except Exception as e:
        log(f"⚠️ 重新加载超时: {e}")
        time.sleep(5)

    new_text, new_secs = get_remaining_time(sb)
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
