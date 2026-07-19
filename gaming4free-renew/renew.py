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
ACCOUNTS = []
for line in os.environ.get("GAME4FREE_ACCOUNT","").split("\n"):
    line = line.strip()
    if not line:
        continue
    parts = line.split("|||")
    if len(parts) >= 3:
        ACCOUNTS.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))

COOKIE = os.environ.get("GAME4FREE_COOKIE","")
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
        page_text = sb.execute_script("return document.body?document.body.innerText.substring(0,2000):'';")
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
        page_text = sb.execute_script("return document.body?document.body.innerText.substring(0,2000):'';")
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
            disabled = bool(sb.execute_script("""
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
        log("❌ 未配置 GAME4FREE_ACCOUNT")
        sys.exit(1)
    
    for server_name, server_slug, email in ACCOUNTS:
        server_url = BASE_URL + server_slug
        
        for browser_attempt in range(max_browser_retries):
            sb = None
            try:
                log(f"🚀 正在启动浏览器 (第 {browser_attempt+1}/{max_browser_retries} 次尝试)...")
                
                sb = SB(uc=True, headless=False, browser='chrome', agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                
                with sb:
                    log(f"🌐 正在访问续期页面 (第 {browser_attempt+1}/{max_browser_retries} 次尝试): {server_url}")
                    sb.open_url(server_url)
                    log(f"📄 当前页面标题: {sb.get_title()}")
                    
                    # 注入 Cookie
                    if COOKIE:
                        log("🍪 正在注入浏览器 Cookie 凭证...")
                        sb.driver.add_cookie({"name":"XSRF-TOKEN","value":"%22eyJpdiI6IjJhQ2R6ZmVnM2R4a0RjV09zZ3B3V1E9PSIsInZhbHVlIjoia3Z0Q3N3cG10ZlV5TnRrN0R3Q1FkU0Z4VjNpQkVJYjJjQlB3a2xkSEJ2eGJYR3l1UzNkQm91UmxVUjNqR1JhS21yYjN4eFRlU0JnZUJhNlBGM2x5a0dVZnVnZ3h6ZjR2YjB3c0JhZjhYU1h3aEh5N0xhT2JxT3JFZG5hVzBZT3V2S1EiLCJtYWMiOiI1M2YwNjM0ZjBiMWQ4ZjIyZmM2NjQ1Y2IyY2RhZWI4N2U1OGIyZjI5NjI4ZjJmYjI2MjA5YmVjZjQ4YjBhNDcyIiwidGFnIjoiIn0%22","domain":".gaming4free.net","path":"/","secure":True})
                        sb.driver.add_cookie({"name":"g4f_session", "value":COOKIE, "domain":".gaming4free.net", "path":"/", "secure":True})
                        log("✅ Cookie 凭证注入完成")
                        time.sleep(2)
                    
                    # 等待组件挂载
                    log("⏳ 等待 Livewire/Alpine 组件完全挂载...")
                    time.sleep(1)
                    
                    # 刷新页面
                    sb.refresh()
                    time.sleep(3)
                    
                    log(f"🔑 准备执行账号操作: {server_name}")
                    
                    # 等待页面加载
                    log("⏳ 等待页面组件完全加载 (最多15秒)...")
                    time.sleep(15)
                    
                    # 获取续期前时间
                    log("⏳ 等待页面完全渲染以获取初始时间...")
                    before_lt, before_ls = get_remaining_time(sb)
                    log(f"⏱️ 续期前剩余时长: {before_lt} ({before_ls}秒)")
                    
                    # 检查按钮冷却
                    cooldown_info = check_button_cooldown(sb)
                    if cooldown_info and cooldown_info.get('cooldown'):
                        remaining = cooldown_info.get('remaining', 0)
                        log(f"⏳ 按钮冷却中，剩余 {remaining}秒，等待...")
                        time.sleep(min(remaining, 300))
                    
                    # 点击 +90 min
                    log("🖱️ 正在寻找并点击 +90 分钟续期按钮...")
                    click_result = sb.execute_script("""
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
                        # 等待 Turnstile
                        log("⏳ 等待 Turnstile 验证...")
                        for tw in range(20):
                            time.sleep(1)
                            try:
                                ts_present = bool(sb.execute_script("""
                                    return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                        || !!document.querySelector('.cf-turnstile')
                                        || (document.body && document.body.innerText.includes("请验证您是真人"));
                                """))
                            except:
                                ts_present = False
                            if ts_present:
                                log("🛡️ 检测到 Turnstile，处理验证...")
                                try:
                                    sb.uc_gui_click_captcha()
                                    time.sleep(3)
                                    log("✅ Turnstile 验证完成")
                                except:
                                    log("⚠️ uc_gui_click_captcha 失败")
                                break
                        
                        time.sleep(5)
                        
                        # 刷新页面
                        log("🔄 刷新页面验证续期结果...")
                        sb.refresh()
                        time.sleep(5)
                        
                        # 获取续期后时间
                        after_lt, after_ls = get_remaining_time(sb)
                        diff = after_ls - before_ls
                        
                        log(f"⏱️ 续期后时间: {after_lt} ({after_ls}秒)，增加: {diff}秒")
                        
                        if diff > 0:
                            log(f"✅ 续期成功！时间增加 {diff}秒 ({before_lt} → {after_lt})")
                            send_tg(f"✅ Pro续期成功 (+{diff}s)", server_name, after_lt)
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
