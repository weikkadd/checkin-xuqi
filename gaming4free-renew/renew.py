#!/usr/bin/env python3
"""
Gaming4Free Renew Pro v10 - 自动续期脚本
拆分自单文件，避免 GitHub Actions autocrlf 压缩问题
"""
import os, sys, time, re, json, traceback, urllib.parse, urllib.request
from datetime import datetime

try:
    from seleniumbase import SB
except ImportError:
    print("seleniumbase not installed. Run: pip install seleniumbase")
    sys.exit(1)

from utils import log, screenshot, parse_countdown_seconds
from utils import get_remaining_time
from cooldown import check_button_cooldown
from tg_notify import send_tg
from config import SERVERS

MAX_BROWSER_RETRIES = 3
# 续期阈值: 剩余 < 45 小时才触发续期
RENEW_THRESHOLD_SECONDS = 45 * 3600


def main():
    log("========== 开始处理服务器账号 ==========")
    if not SERVERS:
        log("❌ 未配置 GAME4FREE_RENEW_URL + GAME4FREE_COOKIE 或 GAME4FREE_ACCOUNTS")
        log("请检查 Secrets 配置")
        sys.exit(1)

    for server_name, server_url, server_cookie in SERVERS:
        for browser_attempt in range(MAX_BROWSER_RETRIES):
            try:
                log(f"🚀 正在启动浏览器 (第 {browser_attempt+1}/{MAX_BROWSER_RETRIES} 次尝试)...")
                # ★ 关键: SB() 是 context manager, 必须用 with...as sb
                # 不能用 sb = SB(...); driver = sb.driver (会报 _GeneratorContextManager 错误)
                with SB(uc=True, headless=False, browser='chrome',
                        agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as sb:
                    driver = sb.driver

                    log(f"🌐 正在访问续期页面 (第 {browser_attempt+1}/{MAX_BROWSER_RETRIES} 次尝试): {server_url}")
                    driver.get(server_url)
                    log(f"📄 当前页面标题: {driver.title}")

                    if server_cookie:
                        log("🍪 正在注入浏览器 Cookie 凭证...")
                        # 用完整 Cookie 字符串注入 (支持任意字段, 包括 HttpOnly)
                        injected = 0
                        for item in server_cookie.split(";"):
                            item = item.strip()
                            if not item or "=" not in item:
                                continue
                            name, value = item.split("=", 1)
                            try:
                                driver.add_cookie({
                                    "name": name.strip(),
                                    "value": value.strip(),
                                    "domain": ".gaming4free.net",
                                    "path": "/",
                                })
                                injected += 1
                            except: pass
                        log(f"✅ 注入 {injected} 个 Cookie")

                    log("🔄 刷新页面让 Cookie 生效...")
                    driver.refresh()
                    time.sleep(5)
                    log(f"📄 刷新后页面标题: {driver.title}")

                    if "Login" in driver.title:
                        log("⚠️ 仍在登录页, Cookie 可能失效或字段不完整")
                        log("⚠️ 请确认 Cookie 包含 XSRF-TOKEN 和 gaming4free_session")

                    log(f"🔑 准备执行账号操作: {server_name}")
                    log("⏳ 等待页面组件完全加载 (最多15秒)...")
                    time.sleep(15)

                    log("⏳ 等待页面完全渲染以获取初始时间...")
                    before_lt, before_ls = get_remaining_time(driver)
                    log(f"⏱️ 续期前剩余时长: {before_lt} ({before_ls}秒)")

                    # ★ 阈值判断: 剩余 > 45 小时直接跳过
                    if before_ls > RENEW_THRESHOLD_SECONDS:
                        log(f"✅ 剩余 {before_lt} > 45h 阈值, 跳过续期")
                        send_tg(f"✅ 跳过 (剩余 {before_lt} > 45h)", server_name, before_lt)
                        break

                    log(f"⏬ 剩余 {before_lt} ≤ 45h 阈值, 开始续期流程...")

                    cooldown_info = check_button_cooldown(driver)
                    if cooldown_info and cooldown_info.get('cooldown'):
                        remaining = cooldown_info.get('remaining', 0)
                        log(f"⏳ 按钮冷却中，剩余 {remaining}秒，等待...")
                        time.sleep(min(remaining, 300))

                    # ★ 用 Selenium 原生 click (isTrusted=true, Livewire 3 需要)
                    log("🖱️ 正在寻找并点击 +90 分钟续期按钮...")
                    click_result = "not-found"
                    try:
                        from selenium.webdriver.common.by import By
                        xpath_candidates = [
                            "//button[contains(., 'watch ad') and contains(., '90')]",
                            "//button[contains(., '+ 90 min')]",
                            "//button[contains(., '+90 min')]",
                            "//button[contains(., '90 min') and not(contains(., '+0'))]",
                        ]
                        for xpath in xpath_candidates:
                            try:
                                btns = driver.find_elements(By.XPATH, xpath)
                                for btn in btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        log(f"🎯 找到按钮: {btn.text}, 用 Selenium 原生 click")
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                                        time.sleep(0.3)
                                        btn.click()
                                        click_result = f"clicked:{btn.text}"
                                        break
                                if click_result != "not-found":
                                    break
                            except Exception as e:
                                continue
                    except Exception as e:
                        log(f"⚠️ Selenium 原生点击失败, fallback 到 JS: {e}")

                    # Fallback: JS click
                    if click_result == "not-found":
                        click_result = driver.execute_script("""
                            var btns = document.querySelectorAll('button, [role="button"]');
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

                    if 'clicked' not in click_result:
                        log("❌ 未找到 +90 min 按钮")
                        send_tg("❌ 未找到续期按钮", server_name, before_lt)
                        break

                    # 等 3 秒看按钮是否变成 loading
                    time.sleep(3)
                    try:
                        after_btns = driver.execute_script("""
                            var btns = document.querySelectorAll('button');
                            var arr = [];
                            for (var i = 0; i < btns.length; i++) {
                                var t = (btns[i].innerText || '').trim();
                                if (t && (t.toLowerCase().indexOf('90') !== -1 || t.toLowerCase().indexOf('loading') !== -1)) {
                                    arr.push(t.substring(0, 80));
                                }
                            }
                            return arr;
                        """)
                        log(f"🐛 +90 min 按钮当前文字: {after_btns}")
                    except: pass

                    log("⏳ 等待 Turnstile 验证...")
                    ts_detected = False
                    for tw in range(30):
                        try:
                            ts_present = bool(driver.execute_script("""
                                return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                    || !!document.querySelector('.cf-turnstile')
                                    || (document.body && document.body.innerText.toLowerCase().indexOf("verify") !== -1);
                            """))
                        except:
                            ts_present = False
                        if ts_present:
                            log(f"🛡️ [{tw+1}秒] 检测到 Turnstile")
                            ts_detected = True
                            break
                        time.sleep(1)

                    if ts_detected:
                        log("⏳ 等 Turnstile 通过 (最多 20 秒, 检测 iframe 消失)...")
                        for wait in range(20):
                            try:
                                gone = not bool(driver.execute_script("""
                                    return !!document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                                        || !!document.querySelector('.cf-turnstile');
                                """))
                                if gone:
                                    log(f"✅ [{wait+1}秒] Turnstile 已通过 (iframe 消失)")
                                    break
                            except:
                                pass
                            time.sleep(1)
                        time.sleep(5)
                    else:
                        log("ℹ️ 未检测到 Turnstile，直接继续")
                        time.sleep(5)

                    # ★ 用 uc_open_with_reconnect 兜底重连 (Turnstile 通过后浏览器可能断连)
                    log("🔄 用 uc_open_with_reconnect 兜底重连...")
                    try:
                        sb.uc_open_with_reconnect(server_url, reconnect_time=12)
                        time.sleep(5)
                        log(f"✅ reconnect 成功, 页面标题: {driver.title}")
                    except Exception as e:
                        log(f"⚠️ reconnect 失败: {str(e)[:100]}")

                    log("🔄 用 driver.refresh() 刷新页面验证续期结果...")
                    try:
                        driver.refresh()
                        time.sleep(5)
                    except Exception as e:
                        log(f"⚠️ refresh 失败: {e}")
                        time.sleep(10)

                    after_lt, after_ls = get_remaining_time(driver)
                    diff = after_ls - before_ls

                    log(f"⏱️ 续期后时间: {after_lt} ({after_ls}秒)，增加: {diff}秒")

                    if diff > 0:
                        log(f"✅ 续期成功！时间增加 {diff}秒 ({before_lt} → {after_lt})")
                        send_tg(f"✅ 续期成功 (+{diff//60}分钟)", server_name, after_lt)
                    elif after_ls == 0:
                        log(f"⚠️ 时间读不到 (Chrome 崩溃), 但续期请求已提交, 可能成功")
                        send_tg(f"⚠️ 续期可能成功 (Chrome 崩溃无法验证, 请看面板)", server_name, before_lt)
                    elif diff > -300:
                        log(f"⚠️ 时间微减 {diff}秒 (< 5分钟), 可能是页面加载延迟, 续期可能成功")
                        send_tg(f"⚠️ 续期可能成功 (时间差小, 请看面板)", server_name, after_lt)
                    else:
                        log(f"❌ 续期失败！时间减少 {abs(diff)}秒 ({before_lt} → {after_lt})")
                        send_tg(f"❌ 续期失败 (-{abs(diff)//60}分钟)", server_name, after_lt)

                    # 成功跑完一轮, 跳出 browser_attempt 循环
                    break

            except Exception as e:
                log(f"❌ 服务器 '{server_name}' 执行异常: {e}")
                try:
                    screenshot(sb, "错误截图")
                except: pass
                send_tg(f"❌ 执行异常: {e}", server_name)
                break


if __name__ == "__main__":
    main()
