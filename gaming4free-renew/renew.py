#!/usr/bin/env python3
"""
Gaming4Free Renew Pro v10 - 自动续期脚本
- 单次点击 + 刷新验证，不循环轰炸
- 多层冷却检测 (expires + cd + disabled)
- Cloudflare Turnstile 自动处理
- TG 通知面板格式
"""
import os, sys, time, re, json, traceback
from datetime import datetime

try:
    from seleniumbase import SB
except ImportError:
    print("seleniumbase not installed. Run: pip install seleniumbase")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────
# 单账号模式 (URL + Cookie 分开, 推荐): GAME4FREE_RENEW_URL + GAME4FREE_COOKIE
# 多账号模式 (可选): GAME4FREE_ACCOUNTS, 每行 "名称|||URL|||Cookie"
RENEW_URL = os.environ.get("GAME4FREE_RENEW_URL","").strip()
COOKIE = os.environ.get("GAME4FREE_COOKIE","").strip()

ACCOUNTS = []
# 优先多账号
for line in os.environ.get("GAME4FREE_ACCOUNTS","").split("\n"):
    line = line.strip()
    if not line:
        continue
    parts = line.split("|||")
    if len(parts) >= 3:
        ACCOUNTS.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    elif len(parts) == 2:
        # 只有 URL|||Cookie, 名称用默认
        ACCOUNTS.append((f"server-{len(ACCOUNTS)+1}", parts[0].strip(), parts[1].strip()))

# 单账号兜底
if not ACCOUNTS and RENEW_URL and COOKIE:
    ACCOUNTS.append(("我的服务器", RENEW_URL, COOKIE))

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN","")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID","")

SUCCESS_ADD_SECONDS = 3000
VERIFY_TIMEOUT = 300
MAX_ROUNDS = 1
RETRY_AFTER_FAIL = True
browser_retry_delay = 5
max_browser_retries = 3

BASE_URL = "https://control.gaming4free.net/server/"

# ── 工具函数 ──────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{ts} {msg}")

def screenshot(sb, name="screenshot"):
    try:
        out_dir = os.path.join(os.path.dirname(__file__), "debug_output")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{name}.png")
        sb.save_screenshot(path)
        log(f"📸 截图已保存至 {path}")
    except:
        pass

def send_tg(message, server_name="", time_text=""):
    """发送 Telegram 通知 — 紧凑面板格式"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        # 邮箱脱敏
        masked = ""
        if ACCOUNTS:
            email = ACCOUNTS[0][2]
            if "@" in email:
                local, domain = email.rsplit("@", 1)
                if len(local) > 3:
                    masked = local[:2] + "****" + local[-2:] + "@" + domain
                else:
                    masked = local + "****@" + domain
        else:
            masked = "****"
        
        # 格式化时间
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        msg = (
            f"🎮Gaming4Free Pro\n"
            f"🖥️服务器: {server_name}\n"
            f"⏰时间: {now}\n"
            f"📊状态: {message}\n"
            f"⏱剩余: {time_text}\n"
            f"⚙️模式: Renew-Pro v10"
        )
        
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        import urllib.request
        data = f"chat_id={TG_CHAT_ID}&text={urllib.parse.quote(msg)}&parse_mode=HTML".encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/x-www-form-urlencoded"})
        resp = urllib.request.urlopen(req, timeout=10)
        log(f"📨 TG 通知成功")
    except Exception as e:
        log(f"⚠️ TG 通知失败: {e}")

def parse_countdown_seconds(match_str):
    """解析时间字符串为秒数"""
    if not match_str:
        return 0
    # HH:MM:SS
    m = re.match(r'(\d+):(\d+):(\d+)', match_str)
    if m:
        return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    # H:M:S
    m = re.match(r'(\d+):(\d+):(\d+)', match_str)
    if m:
        return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    # Xm or Xh
    m = re.match(r'(\d+)\s*m', match_str, re.I)
    if m:
        return int(m.group(1)) * 60
    m = re.match(r'(\d+)\s*h', match_str, re.I)
    if m:
        return int(m.group(1)) * 3600
    return 0

def get_remaining_time(sb):
    """获取页面剩余时间（秒）和文本"""
    try:
        # 用 sb.driver.execute_script 走标准 Selenium (支持顶层 return)
        page_text = sb.driver.execute_script("return document.body?document.body.innerText.substring(0,2000):'';")
        if not page_text:
            return ("(未知)", 0)
        time_matches = re.findall(r'(\d{1,2}:\d{2}:\d{2})', page_text)
        if time_matches:
            lt = time_matches[0]
            ls = parse_countdown_seconds(lt)
            return (lt, ls)
        return ("(未找到)", 0)
    except Exception as e:
        log(f"⚠️ 获取时间失败: {e}")
        return ("(错误)", 0)

def check_button_cooldown(sb):
    """检查续期按钮是否冷却"""
    try:
        page_text = sb.driver.execute_script("return document.body?document.body.innerText.substring(0,2000):'';")
        if not page_text:
            return None
        
        # 策略1: 匹配 "expires XX:XX" (不含 AM/PM)
        exp_no_ampm = re.search(r'expires\s+(\d{1,2}:\d{2})(?!\s*[APap][Mm])', page_text, re.I)
        if exp_no_ampm:
            hhmm = exp_no_ampm.group(1)
            parts = hhmm.split(':')
            if len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                remaining_sec = hours * 3600 + minutes * 60
                log(f"⏳ 检测到冷却 (expires): {hhmm} (剩余 {remaining_sec}秒)")
                return {'cooldown': True, 'remaining': remaining_sec, 'text': hhmm}
        
        # 策略1.5: 匹配 "XX:XX cd" 格式
        cd_match = re.search(r'(\d+):(\d+)\s+cd', page_text, re.I)
        if cd_match:
            mins = int(cd_match.group(1))
            secs = int(cd_match.group(2))
            remaining_sec = mins * 60 + secs
            log(f"⏳ 检测到按钮冷却倒计时: {cd_match.group(0).strip()} (剩余 {remaining_sec}秒)")
            return {'cooldown': True, 'remaining': remaining_sec, 'text': cd_match.group(0).strip()}
        
        # 策略2: 检查按钮 disabled 状态
        try:
            disabled = bool(sb.driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var txt = (btns[i].innerText || btns[i].textContent || '').trim();
                    if (txt.indexOf('90') !== -1 || txt.indexOf('+ 90') !== -1 || txt.indexOf('+90') !== -1) {
                        return btns[i].disabled;
                    }
                }
                return false;
            """))
            if disabled:
                log("⏳ 检测到按钮 disabled 状态")
                return {'cooldown': True, 'remaining': 0, 'text': 'disabled'}
        except:
            pass
        
        return None
    except Exception as e:
        log(f"⚠️ 检查按钮冷却失败: {e}")
        return None

def handle_turnstile(sb, max_retries=3):
    """处理 Cloudflare Turnstile 验证"""
    for attempt in range(max_retries):
        try:
            if sb.uc_gui_click_captcha():
                time.sleep(3)
                log(f"✅ Turnstile 验证通过 (UC 模式)")
                return True
        except Exception as e:
            log(f"⚠️ UC 模式失败: {e}")
    
    log("❌ Turnstile 验证全部失败")
    return False

# ── 主流程 ────────────────────────────────────────────
def main():
    log("========== 开始处理服务器账号 ==========")

    if not ACCOUNTS:
        log("❌ 未配置账号信息")
        log("   单账号: 配置 GAME4FREE_RENEW_URL + GAME4FREE_COOKIE 两个 Secret")
        log("   多账号: 配置 GAME4FREE_ACCOUNTS, 每行 '名称|||URL|||Cookie'")
        sys.exit(1)

    for server_name, server_url, cookie_str in ACCOUNTS:
        # server_url 已经是完整 URL, 不需要 BASE_URL 拼接
        if not server_url.startswith("http"):
            server_url = BASE_URL + server_url

        for browser_attempt in range(max_browser_retries):
            try:
                log(f"🚀 正在启动浏览器 (第 {browser_attempt+1}/{max_browser_retries} 次尝试)...")

                with SB(uc=True, headless=False, browser='chrome', agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as sb:
                    log(f"🌐 正在访问续期页面 (第 {browser_attempt+1}/{max_browser_retries} 次尝试): {server_url}")
                    sb.open_url(server_url)
                    log(f"📄 当前页面标题: {sb.get_title()}")

                    # 注入完整 Cookie 字符串 (格式: name1=value1; name2=value2; ...)
                    if cookie_str:
                        log("🍪 正在注入浏览器 Cookie 凭证...")
                        # 用 Selenium add_cookie API 注入 (比 document.cookie 更可靠)
                        # add_cookie 会自动加到当前域, 且支持 HttpOnly 字段
                        injected = 0
                        for item in cookie_str.split(";"):
                            item = item.strip()
                            if not item or "=" not in item:
                                continue
                            name, value = item.split("=", 1)
                            name = name.strip()
                            value = value.strip()
                            if not name:
                                continue
                            try:
                                sb.driver.add_cookie({
                                    "name": name,
                                    "value": value,
                                    "domain": ".gaming4free.net",
                                    "path": "/",
                                })
                                injected += 1
                            except Exception as e:
                                log(f"  ⚠️ Cookie [{name}] 注入失败: {e}")
                        log(f"✅ 注入 {injected} 个 Cookie")

                    # 等待组件挂载
                    log("⏳ 等待 Livewire/Alpine 组件完全挂载...")
                    time.sleep(1)

                    # 刷新页面让 Cookie 生效
                    log("🔄 刷新页面让 Cookie 生效...")
                    sb.refresh()
                    time.sleep(5)

                    # 检查登录状态
                    page_title = sb.get_title()
                    log(f"📄 刷新后页面标题: {page_title}")
                    if "Login" in page_title:
                        log("⚠️ 仍在登录页, Cookie 可能失效或字段不完整")
                        log("⚠️ 请确认 Cookie 包含 XSRF-TOKEN 和 gaming4free_session")
                    
                    log(f"🔑 准备执行账号操作: {server_name}")
                    
                    # 等待页面加载
                    log("⏳ 等待页面组件完全加载 (最多15秒)...")
                    time.sleep(15)
                    
                    # 获取续期前时间
                    log("⏳ 等待页面完全渲染以获取初始时间...")
                    before_lt, before_ls = get_remaining_time(sb)
                    log(f"⏱️ 续期前剩余时长: {before_lt} ({before_ls}秒)")

                    # 诊断: 打印页面文本前 500 字符, 看按钮是否存在
                    try:
                        diag_text = sb.driver.execute_script("return document.body?document.body.innerText.substring(0,500):'';")
                        log(f"🐛 页面文本前 500 字符:\n{diag_text}")
                        # 列出所有 button 文字
                        btn_texts = sb.driver.execute_script("""
                            var btns = document.querySelectorAll('button');
                            var arr = [];
                            for (var i = 0; i < btns.length; i++) {
                                var t = (btns[i].innerText || btns[i].textContent || '').trim();
                                if (t) arr.push(t.substring(0, 50));
                            }
                            return arr;
                        """)
                        log(f"🐛 页面所有按钮: {btn_texts}")
                    except Exception as e:
                        log(f"⚠️ 诊断失败: {e}")

                    # 检查按钮冷却
                    cooldown_info = check_button_cooldown(sb)
                    if cooldown_info and cooldown_info.get('cooldown'):
                        remaining = cooldown_info.get('remaining', 0)
                        log(f"⏳ 按钮冷却中，剩余 {remaining}秒，等待...")
                        time.sleep(min(remaining, 300))
                    
                    # 点击 +90 min — 用 Selenium 原生 click (isTrusted=true)
                    # JS element.click() 在 Livewire 3 下 isTrusted=false 会被忽略
                    log("🖱️ 正在寻找并点击 +90 分钟续期按钮...")
                    click_result = "not-found"
                    try:
                        # 用 XPath 找按钮, 然后用 Selenium 原生 click
                        from selenium.webdriver.common.by import By
                        xpath_candidates = [
                            "//button[contains(., 'watch ad') and contains(., '90')]",
                            "//button[contains(., '+ 90 min')]",
                            "//button[contains(., '+90 min')]",
                            "//button[contains(., '90 min') and not(contains(., '+0'))]",
                        ]
                        for xpath in xpath_candidates:
                            try:
                                btns = sb.driver.find_elements(By.XPATH, xpath)
                                for btn in btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        log(f"🎯 找到按钮: {btn.text}, 用 Selenium 原生 click")
                                        sb.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                                        time.sleep(0.3)
                                        btn.click()  # ★ Selenium 原生 click, isTrusted=true
                                        click_result = f"clicked:{btn.text}"
                                        break
                                if click_result != "not-found":
                                    break
                            except Exception as e:
                                log(f"⚠️ XPath {xpath} 失败: {e}")
                                continue
                    except Exception as e:
                        log(f"⚠️ Selenium 原生点击失败, fallback 到 JS: {e}")
                        # Fallback: JS click
                        if click_result == "not-found":
                            click_result = sb.driver.execute_script("""
                                var btns = document.querySelectorAll('button');
                                for (var i = 0; i < btns.length; i++) {
                                    var txt = (btns[i].innerText || btns[i].textContent || '').trim();
                                    if (txt.indexOf('90') !== -1 || txt.indexOf('+ 90') !== -1 || txt.indexOf('+90') !== -1) {
                                        btns[i].scrollIntoView({block: 'center'});
                                        btns[i].removeAttribute('disabled');
                                        btns[i].style.cssText += '; pointer-events:auto !important;';
                                        btns[i].click();
                                        return 'clicked:' + txt;
                                    }
                                }
                                return 'not-found';
                            """)
                    log(f"🎯 点击结果: {click_result}")
                    
                    if click_result == 'not-found':
                        log("❌ 未找到 +90 min 按钮，跳过本轮")
                        send_tg("❌ 未找到续期按钮", server_name, before_lt)
                        account_finished = True
                    else:
                        # 等 2 秒让 modal 弹出
                        time.sleep(2)

                        # 诊断: 打印当前所有按钮
                        try:
                            modal_btns = sb.driver.execute_script("""
                                var btns = document.querySelectorAll('button');
                                var arr = [];
                                for (var i = 0; i < btns.length; i++) {
                                    var t = (btns[i].innerText || btns[i].textContent || '').trim();
                                    if (t) arr.push(t.substring(0, 80));
                                }
                                return arr;
                            """)
                            log(f"🐛 点击后页面按钮: {modal_btns}")
                        except: pass

                        # ★ 关键修复: 不点 Enable Ads (那是首次设置广告的入口, 会取消当前续期)
                        # 点 +90 min 后按钮会变成 'loading…' 表示续期已开始
                        # 直接等 Turnstile 出现即可
                        log("⏳ +90 min 已点击, 等待 loading 完成 + Turnstile 出现...")
                        time.sleep(3)

                        # 诊断: 打印点击 +90 min 后的按钮文字
                        try:
                            after_btns = sb.driver.execute_script("""
                                var btns = document.querySelectorAll('button');
                                var arr = [];
                                for (var i = 0; i < btns.length; i++) {
                                    var t = (btns[i].innerText || '').trim();
                                    if (t && t.toLowerCase().indexOf('90') !== -1 || t.toLowerCase().indexOf('loading') !== -1) {
                                        arr.push(t.substring(0, 80));
                                    }
                                }
                                return arr;
                            """)
                            log(f"🐛 +90 min 按钮当前文字: {after_btns}")
                        except: pass

                        # ★ 关键改进: 不调用 uc_gui_click_captcha (会让 Chrome 崩溃)
                        #    改用 uc_open_with_reconnect, SeleniumBase 会自动处理 Turnstile
                        log("⏳ 等待 Turnstile 出现 (最多 15 秒)...")
                        turnstile_appeared = False
                        for tw in range(15):
                            time.sleep(1)
                            try:
                                ts_present = bool(sb.driver.execute_script("""
                                    return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                        || !!document.querySelector('.cf-turnstile')
                                        || (document.body && document.body.innerText.toLowerCase().indexOf("verify") !== -1);
                                """))
                                if ts_present:
                                    log(f"🛡️ [第 {tw+1} 秒] 检测到 Turnstile")
                                    turnstile_appeared = True
                                    break
                            except Exception as e:
                                if "Connection refused" in str(e):
                                    log(f"💀 浏览器崩溃")
                                    break

                        # ★ 关键修复: 等 Turnstile 通过, 然后立即点击 modal 里的提交按钮
                        # Turnstile 通过 = iframe 消失, 但 modal 还在, 需要点 Confirm/Submit
                        if turnstile_appeared:
                            log("⏳ 等 Turnstile 通过 (最多 20 秒, 检测 iframe 消失)...")
                            turnstile_passed = False
                            for wait_tw in range(20):
                                time.sleep(1)
                                try:
                                    ts_still = bool(sb.driver.execute_script("""
                                        return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                            || !!document.querySelector('.cf-turnstile');
                                    """))
                                    if not ts_still:
                                        log(f"✅ [第 {wait_tw+1} 秒] Turnstile 已通过 (iframe 消失)")
                                        turnstile_passed = True
                                        break
                                    if wait_tw % 5 == 4:
                                        log(f"⏳ [第 {wait_tw+1} 秒] Turnstile 仍在...")
                                except Exception as e:
                                    if "Connection refused" in str(e):
                                        log(f"💀 等待 Turnstile 时浏览器崩溃")
                                        break
                                    log(f"⚠️ 等待异常: {str(e)[:80]}")

                            # ★ Turnstile 通过后, 立即点击 modal 里的提交按钮
                            if turnstile_passed:
                                log("🖱️ Turnstile 通过, 查找 modal 里的提交按钮...")
                                time.sleep(2)  # 等 modal 更新

                                # 打印 modal 里所有按钮 (诊断)
                                try:
                                    modal_btns = sb.driver.execute_script("""
                                        var btns = document.querySelectorAll('button');
                                        var arr = [];
                                        for (var i = 0; i < btns.length; i++) {
                                            var t = (btns[i].innerText || '').trim();
                                            if (t && btns[i].offsetParent !== null) arr.push(t.substring(0, 80));
                                        }
                                        return arr;
                                    """)
                                    log(f"🐛 Turnstile 通过后可见按钮: {modal_btns}")
                                except: pass

                                # 点击提交按钮 (排除 Cancel/Maybe later/Enable Ads)
                                try:
                                    submit_clicked = sb.driver.execute_script("""
                                        var btns = document.querySelectorAll('button');
                                        // ★ 只点明确的提交关键词, 不点 +90 (会重新触发)
                                        var keywords = ['confirm', 'submit', 'renew', 'claim', 'continue', 'ok', 'yes', 'verify', 'get free time', 'apply'];
                                        var exclude = ['cancel', 'later', 'enable ads', 'sign out', 'back to', '+ 90', '+90', 'watch ad', 'loading'];
                                        for (var i = 0; i < btns.length; i++) {
                                            var t = (btns[i].innerText || '').trim().toLowerCase();
                                            if (btns[i].disabled) continue;
                                            if (btns[i].offsetParent === null) continue;
                                            // 排除关键词
                                            var excluded = false;
                                            for (var e = 0; e < exclude.length; e++) {
                                                if (t.indexOf(exclude[e]) !== -1) { excluded = true; break; }
                                            }
                                            if (excluded) continue;
                                            // 匹配关键词
                                            for (var k = 0; k < keywords.length; k++) {
                                                if (t.indexOf(keywords[k]) !== -1) {
                                                    btns[i].scrollIntoView({block: 'center'});
                                                    btns[i].click();
                                                    return 'clicked:' + btns[i].innerText.trim();
                                                }
                                            }
                                        }
                                        return false;
                                    """)
                                    if submit_clicked:
                                        log(f"✅ 点击提交按钮: {submit_clicked}")
                                        time.sleep(8)  # 等后端处理
                                    else:
                                        log("ℹ️ 没找到 Confirm/Submit 按钮, 续期可能已自动提交 (Livewire 自动确认)")

                                    # 检查 modal 是否关闭
                                    try:
                                        modal_still = bool(sb.driver.execute_script("""
                                            var btns = document.querySelectorAll('button');
                                            for (var i = 0; i < btns.length; i++) {
                                                var t = (btns[i].innerText || '').trim().toLowerCase();
                                                if (t.indexOf('enable ads') !== -1 || t.indexOf('cancel') !== -1) return true;
                                            }
                                            return false;
                                        """))
                                        if not modal_still:
                                            log("🎉 modal 已关闭, 续期已提交!")
                                        else:
                                            log("⚠️ modal 仍在, 可能需要再点其他按钮")
                                    except: pass
                                except Exception as e:
                                    log(f"⚠️ 点击提交按钮失败: {e}")

                        # ★ 用 uc_open_with_reconnect 兜底 (处理可能的浏览器断连)
                        log("🔄 用 uc_open_with_reconnect 兜底重连...")

                        reconnect_ok = False
                        for reconnect_attempt in range(3):
                            try:
                                log(f"🔄 第 {reconnect_attempt+1} 次 reconnect (reconnect_time=12)...")
                                sb.uc_open_with_reconnect(server_url, reconnect_time=12)
                                time.sleep(5)
                                # 测试 driver 是否可用
                                _ = sb.driver.title
                                log(f"✅ 第 {reconnect_attempt+1} 次 reconnect 成功, 页面标题: {_}")
                                reconnect_ok = True
                                break
                            except Exception as e:
                                log(f"⚠️ 第 {reconnect_attempt+1} 次 reconnect 失败: {str(e)[:100]}")
                                time.sleep(3)

                        if not reconnect_ok:
                            log("❌ 3 次 reconnect 都失败, 跳过本轮")
                            send_tg(f"❌ 浏览器无法重连 (Chrome 崩溃)", server_name, before_lt)
                            continue

                        # 重连成功后, 检查是否有 Confirm/Submit 按钮
                        try:
                            current_btns = sb.driver.execute_script("""
                                var btns = document.querySelectorAll('button');
                                var arr = [];
                                for (var i = 0; i < btns.length; i++) {
                                    var t = (btns[i].innerText || '').trim();
                                    if (t && btns[i].offsetParent !== null) arr.push(t.substring(0, 60));
                                }
                                return arr;
                            """)
                            log(f"🐛 reconnect 后可见按钮: {current_btns}")

                            # 点击提交按钮 (如果有)
                            submit_clicked = sb.driver.execute_script("""
                                var btns = document.querySelectorAll('button');
                                var keywords = ['confirm', 'submit', 'renew', 'claim', 'continue', 'ok', 'yes', 'verify', 'get free time', 'apply'];
                                for (var i = 0; i < btns.length; i++) {
                                    var t = (btns[i].innerText || '').trim().toLowerCase();
                                    if (btns[i].disabled) continue;
                                    if (btns[i].offsetParent === null) continue;
                                    for (var k = 0; k < keywords.length; k++) {
                                        if (t.indexOf(keywords[k]) !== -1 && t.indexOf('cancel') === -1 && t.indexOf('later') === -1) {
                                            btns[i].scrollIntoView({block: 'center'});
                                            btns[i].click();
                                            return 'clicked:' + btns[i].innerText.trim();
                                        }
                                    }
                                }
                                return false;
                            """)
                            if submit_clicked:
                                log(f"✅ 点击提交按钮: {submit_clicked}")
                                time.sleep(5)
                        except Exception as e:
                            log(f"⚠️ 检查按钮失败: {e}")

                        # ★ 关键: 不再用 sb.open_url (会触发 CF 检测让 Chrome 崩溃)
                        # reconnect 后页面已经是 Console, 直接用 driver.refresh() 即可
                        log("🔄 用 driver.refresh() 刷新页面验证续期结果...")
                        try:
                            sb.driver.refresh()
                            time.sleep(8)
                            log(f"✅ 刷新成功, 页面标题: {sb.driver.title}")
                        except Exception as e:
                            log(f"⚠️ driver.refresh 失败: {str(e)[:100]}")
                            # 尝试重新 reconnect
                            try:
                                sb.uc_open_with_reconnect(server_url, reconnect_time=8)
                                time.sleep(5)
                                log("✅ fallback reconnect 成功")
                            except Exception as e2:
                                log(f"❌ 所有方式都失败: {str(e2)[:100]}")
                                send_tg(f"❌ 浏览器崩溃: {str(e2)[:100]}", server_name, before_lt)
                                continue

                        # 获取续期后时间
                        after_lt, after_ls = get_remaining_time(sb)
                        diff = after_ls - before_ls

                        log(f"⏱️ 续期后时间: {after_lt} ({after_ls}秒)，增加: {diff}秒")

                        if diff > 0:
                            log(f"✅ 续期成功！时间增加 {diff}秒 ({before_lt} → {after_lt})")
                            send_tg(f"✅ Pro续期成功 (+{diff}s)", server_name, after_lt)
                        elif after_ls == 0:
                            # 时间读不到, 但 modal 已关闭, 可能成功了
                            log(f"⚠️ 时间读不到, 但 modal 已关闭, 可能成功 (请手动确认)")
                            send_tg(f"⚠️ 续期可能成功 (请手动确认)", server_name, before_lt)
                        else:
                            log(f"❌ 续期失败！时间减少 {abs(diff)}秒 ({before_lt} → {after_lt})")
                            send_tg(f"❌ Pro续期失败 (-{abs(diff)}s)", server_name, after_lt)
                        
                        account_finished = True
            
            except Exception as e:
                log(f"❌ 服务器 '{server_name}' 执行异常: {e}")
                try:
                    screenshot(sb, "错误截图")
                except: pass
                send_tg(f"❌ 执行异常: {e}", server_name)
                break

if __name__ == "__main__":
    main()
