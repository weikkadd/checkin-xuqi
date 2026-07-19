#!/usr/bin/env python3
"""
Gaming4Free Renew Pro v13 - 终极优化版
=====================
- 增强：直接调用 Livewire API 触发续期，确保 100% 触发服务器请求
- 增强：深度广告 DOM 监测，自动处理视频和弹窗
- 增强：模拟真人活跃状态，防止广告暂停
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
RENEW_THRESHOLD_SECONDS = 45 * 3600
MAX_ROUNDS = 10

def main():
    log("========== 开始处理服务器账号 (Pro v13) ==========")
    if not SERVERS:
        log("❌ 未配置服务器信息")
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
                    driver.set_page_load_timeout(120)

                    log(f"🌐 访问页面: {server_url}")
                    driver.get(server_url)
                    
                    if server_cookie:
                        log("🍪 注入 Cookie...")
                        for item in server_cookie.split(";"):
                            item = item.strip()
                            if "=" in item:
                                name, value = item.split("=", 1)
                                try: driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".gaming4free.net", "path": "/"})
                                except: pass
                        driver.refresh(); time.sleep(10)

                    current_round = 0
                    while current_round < MAX_ROUNDS:
                        current_round += 1
                        log(f"\n🔄 --- 第 {current_round}/{MAX_ROUNDS} 轮续期 ---")
                        
                        before_lt, before_ls = get_remaining_time(driver)
                        log(f"⏱️ 当前剩余时长: {before_lt} ({before_ls}秒)")
                        
                        if before_ls >= RENEW_THRESHOLD_SECONDS:
                            log(f"✅ 目标时长已达标，停止续期")
                            success_in_this_server = True
                            break

                        # 检查 5 分钟冷却 (05:00 cd)
                        try:
                            page_text = driver.execute_script("return document.body.innerText")
                            if "05:00" in page_text and "cd" in page_text:
                                log("⏳ 侦测到 5 分钟冷却期 (05:00 cd)，强制等待 310 秒...")
                                time.sleep(310); driver.refresh(); time.sleep(10); continue
                        except: pass

                        # 核心策略：直接调用 Livewire API
                        log("🎯 尝试直接通过 Livewire API 触发续期...")
                        try:
                            # 查找组件 ID 并调用 extend 方法
                            lw_result = driver.execute_script("""
                                var btn = document.querySelector('button.rt-btn-free') || document.querySelector('button:contains("90")');
                                if (!btn) {
                                    var allBtns = document.querySelectorAll('button');
                                    for(var i=0; i<allBtns.length; i++) {
                                        if(allBtns[i].innerText.indexOf('90') !== -1) { btn = allBtns[i]; break; }
                                    }
                                }
                                if (btn && window.Livewire) {
                                    var component = Livewire.find(btn.closest('[wire\\\\:id]').getAttribute('wire:id'));
                                    if (component) {
                                        component.call('extend');
                                        return 'success';
                                    }
                                }
                                return 'fail';
                            """)
                            if lw_result == 'success':
                                log("✅ Livewire API 调用成功")
                            else:
                                log("⚠️ Livewire 调用失败，回退到模拟点击")
                                driver.execute_script("document.querySelector('button.rt-btn-free').click();")
                        except Exception as e:
                            log(f"⚠️ 触发续期异常: {e}")

                        # 处理验证码
                        time.sleep(5)
                        try:
                            if driver.find_elements('css selector', 'iframe[src*="challenges.cloudflare.com"]'):
                                log("🛡️ 等待 Turnstile 验证...")
                                for _ in range(30):
                                    if not driver.find_elements('css selector', 'iframe[src*="challenges.cloudflare.com"]'):
                                        log("✅ Turnstile 已通过")
                                        break
                                    time.sleep(1)
                        except: pass
                        
                        # 深度广告监测与等待
                        log("🎬 监测广告播放中...")
                        start_wait = time.time()
                        while time.time() - start_wait < 90:
                            # 模拟真人活跃，防止广告暂停
                            driver.execute_script("window.dispatchEvent(new Event('mousemove'));")
                            
                            # 检查是否有广告弹窗需要关闭
                            try:
                                driver.execute_script("""
                                    var closeBtns = document.querySelectorAll('[aria-label="Close"], .modal-close, button:contains("Close")');
                                    for(var i=0; i<closeBtns.length; i++) {
                                        if(closeBtns[i].offsetParent !== null) closeBtns[i].click();
                                    }
                                """)
                            except: pass
                            
                            # 检查时间是否已经增加 (提前跳出)
                            if (time.time() - start_wait) > 30 and (int(time.time() - start_wait) % 15 == 0):
                                _, check_ls = get_remaining_time(driver)
                                if check_ls > before_ls + 3000:
                                    log("🎉 检测到时间已增加，广告提前结束")
                                    break
                            
                            time.sleep(2)

                        # 最终刷新并验证
                        log("🔄 刷新页面同步状态...")
                        driver.refresh(); time.sleep(12)
                        after_lt, after_ls = get_remaining_time(driver)
                        diff = after_ls - before_ls
                        
                        if diff > 3000:
                            log(f"✅ 第 {current_round} 轮成功！新时间: {after_lt}")
                            send_tg(f"✅ 续期成功 (第{current_round}轮)", server_name, after_lt)
                        else:
                            log(f"❌ 第 {current_round} 轮失败，时间未增加")
                            # 失败后尝试重连浏览器环境
                            try: sb.uc_open_with_reconnect(server_url, reconnect_time=10); time.sleep(10)
                            except: pass

                    log(f"🏁 账号 {server_name} 处理结束")
                    break

            except Exception as e:
                log(f"❌ 运行异常: {e}")
                time.sleep(10)

if __name__ == "__main__":
    main()
