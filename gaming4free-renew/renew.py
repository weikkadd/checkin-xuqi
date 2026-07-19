#!/usr/bin/env python3
"""
Gaming4Free Renew Pro v12 - 自动续期脚本 (Manus 优化版)
=====================
- 修复：修正 'log' 未定义的语法错误
- 增强：优化循环续期逻辑，增加超时容错
- 增强：加入广告观看等待 (70s)，确保奖励发放
"""
import os, sys, time, re, json, traceback, urllib.parse, urllib.request
from datetime import datetime

try:
    from seleniumbase import SB
except ImportError:
    print("seleniumbase not installed. Run: pip install seleniumbase")
    sys.exit(1)

# 统一导入
from utils import log, screenshot, parse_countdown_seconds
from utils import get_remaining_time
from cooldown import check_button_cooldown
from tg_notify import send_tg
from config import SERVERS

MAX_BROWSER_RETRIES = 3
RENEW_THRESHOLD_SECONDS = 45 * 3600
MAX_ROUNDS = 10

def main():
    log("========== 开始处理服务器账号 ==========")
    if not SERVERS:
        log("❌ 未配置服务器信息，请检查 Secrets")
        sys.exit(1)

    for server_name, server_url, server_cookie in SERVERS:
        log(f"\n🔑 准备执行账号操作: {server_name}")
        
        success_in_this_server = False
        for browser_attempt in range(MAX_BROWSER_RETRIES):
            if success_in_this_server: break
            
            try:
                log(f"🚀 启动浏览器 (第 {browser_attempt+1}/{MAX_BROWSER_RETRIES} 次尝试)...")
                with SB(uc=True, headless=False, browser='chrome',
                        agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as sb:
                    driver = sb.driver
                    driver.set_page_load_timeout(120) # 增加页面加载超时

                    log(f"🌐 访问页面: {server_url}")
                    try:
                        driver.get(server_url)
                    except Exception as e:
                        log(f"⚠️ 页面加载超时或异常: {e}")
                        continue
                    
                    if server_cookie:
                        log("🍪 注入 Cookie...")
                        for item in server_cookie.split(";"):
                            item = item.strip()
                            if "=" in item:
                                name, value = item.split("=", 1)
                                try:
                                    driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".gaming4free.net", "path": "/"})
                                except: pass
                        driver.refresh(); time.sleep(10)

                    current_round = 0
                    while current_round < MAX_ROUNDS:
                        current_round += 1
                        log(f"\n🔄 --- 第 {current_round}/{MAX_ROUNDS} 轮续期 ---")
                        
                        # 获取当前时间
                        try:
                            before_lt, before_ls = get_remaining_time(driver)
                        except:
                            log("⚠️ 获取时间失败，尝试刷新...")
                            driver.refresh(); time.sleep(10)
                            before_lt, before_ls = get_remaining_time(driver)
                            
                        log(f"⏱️ 当前剩余时长: {before_lt} ({before_ls}秒)")
                        
                        if before_ls >= RENEW_THRESHOLD_SECONDS:
                            log(f"✅ 目标时长已达标，停止续期")
                            success_in_this_server = True
                            break

                        # 检查冷却
                        cooldown_info = check_button_cooldown(driver)
                        if cooldown_info and cooldown_info.get('cooldown'):
                            remaining = cooldown_info.get('remaining', 120)
                            log(f"⏳ 按钮冷却中，等待 {remaining} 秒...")
                            time.sleep(remaining + 5)
                            driver.refresh(); time.sleep(10)
                            continue

                        # 点击按钮
                        log("🖱️ 寻找并点击续期按钮...")
                        click_done = False
                        try:
                            from selenium.webdriver.common.by import By
                            xpath_candidates = [
                                "//button[contains(., 'watch ad') and contains(., '90')]",
                                "//button[contains(., '+ 90 min')]",
                                "//button[contains(., '90 min')]"
                            ]
                            for xpath in xpath_candidates:
                                btns = driver.find_elements(By.XPATH, xpath)
                                for btn in btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                                        time.sleep(1); btn.click()
                                        click_done = True; break
                                if click_done: break
                        except Exception as e:
                            log(f"⚠️ 点击异常: {e}")

                        if not click_done:
                            log("❌ 未找到有效续期按钮，尝试刷新页面...")
                            driver.refresh(); time.sleep(10); continue

                        # 处理验证码
                        log("⏳ 等待 Turnstile 验证...")
                        time.sleep(5)
                        try:
                            ts_iframes = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="challenges.cloudflare.com"]')
                            if ts_iframes:
                                log("🛡️ 检测到 Turnstile，等待通过...")
                                for _ in range(25):
                                    if not driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="challenges.cloudflare.com"]'):
                                        log("✅ Turnstile 已通过")
                                        break
                                    time.sleep(1)
                        except: pass
                        
                        # 观看广告等待
                        log("🎬 模拟观看广告 (75秒)...")
                        time.sleep(75)

                        # 刷新并验证
                        log("🔄 刷新页面验证结果...")
                        try:
                            driver.refresh(); time.sleep(12)
                            after_lt, after_ls = get_remaining_time(driver)
                            diff = after_ls - before_ls
                            
                            if diff > 3000:
                                log(f"✅ 第 {current_round} 轮成功！新时间: {after_lt}")
                                send_tg(f"✅ 续期成功 (第{current_round}轮)", server_name, after_lt)
                            else:
                                log(f"⚠️ 第 {current_round} 轮未见明显增加，可能需要重试")
                        except Exception as e:
                            log(f"⚠️ 刷新验证异常: {e}")
                            break # 跳出当前轮次循环，由外层浏览器重试处理

                    log(f"🏁 账号 {server_name} 处理结束")
                    break

            except Exception as e:
                log(f"❌ 运行异常: {e}")
                time.sleep(10)

if __name__ == "__main__":
    main()
