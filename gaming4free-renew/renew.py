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

                    # 诊断: 检查页面状态
                    diag = driver.execute_script("""
                        var info = {
                            livewire: !!window.Livewire,
                            livewireComps: window.Livewire ? window.Livewire.all().length : 0,
                            alpine: !!window.Alpine,
                            pageText: document.body ? document.body.innerText.substring(0, 800) : '',
                            buttonsWith90: [],
                            anyIframe: !!document.querySelector('iframe')
                        };
                        var btns = document.querySelectorAll('button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || '').trim();
                            if (t.indexOf('90') !== -1) {
                                info.buttonsWith90.push({
                                    text: t,
                                    disabled: btns[i].disabled,
                                    visible: btns[i].offsetParent !== null,
                                    className: btns[i].className
                                });
                            }
                        }
                        return JSON.stringify(info);
                    """)
                    log(f"  诊断: {diag}")

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

                        # 核心策略：三层续期触发
                        log("🎯 触发续期...")
                        try:
                            lw_result = driver.execute_script("""
                                // 1. 找到包含 '90' 的按钮
                                var btns = document.querySelectorAll('button');
                                var btn = null, btnText = '';
                                for (var i = 0; i < btns.length; i++) {
                                    var t = (btns[i].innerText || btns[i].textContent || '').trim();
                                    if (t.indexOf('90') !== -1 && btns[i].offsetParent !== null) {
                                        btn = btns[i]; btnText = t; break;
                                    }
                                }
                                if (!btn) return 'no-button';

                                // 2. 在 Livewire 组件列表中匹配按钮文本
                                if (window.Livewire) {
                                    var comps = window.Livewire.all();
                                    for (var c = 0; c < comps.length; c++) {
                                        try {
                                            var snap = comps[c].snapshot;
                                            if (snap && snap.html && snap.html.indexOf(btnText) !== -1) {
                                                comps[c].call('extend');
                                                return 'livewire:' + comps[c].id;
                                            }
                                        } catch(e) {}
                                    }
                                    // 通用 fallback: 遍历所有组件
                                    for (var c2 = 0; c2 < comps.length; c2++) {
                                        try { comps[c2].call('extend'); return 'livewire-generic:' + c2; }
                                        catch(e) {}
                                    }
                                }

                                // 3. 降级: JS 原生 click
                                btn.scrollIntoView({block: 'center'});
                                btn.removeAttribute('disabled');
                                btn.click();
                                return 'native-click';
                            """)
                            log(f"  结果: {lw_result}")
                            if lw_result == 'no-button':
                                log("⚠️ 未找到续期按钮")
                        except Exception as e:
                            log(f"⚠️ 触发续期异常: {e}")

                        # 处理 Turnstile - 等它出现然后尝试自动点击
                        log("🛡️ 检查 Turnstile...")
                        time.sleep(3)
                        turnstile_appeared = False
                        for ts_wait in range(15):
                            has_ts = len(driver.find_elements('css selector', 'iframe[src*="challenges.cloudflare.com"]')) > 0
                            if has_ts:
                                turnstile_appeared = True
                                log(f"  检测到 Turnstile (第{ts_wait+1}秒)，尝试自动点击...")
                                try:
                                    sb.uc_gui_click_captcha()
                                    log("  uc_gui_click_captcha 已执行")
                                    time.sleep(5)
                                except Exception as ex:
                                    log(f"  uc_gui_click_captcha 失败: {ex}")
                                # 检查是否通过了
                                for check in range(10):
                                    if len(driver.find_elements('css selector', 'iframe[src*="challenges.cloudflare.com"]')) == 0:
                                        log("  Turnstile 已通过!")
                                        break
                                    time.sleep(2)
                                break
                            time.sleep(1)
                        if not turnstile_appeared:
                            log("  未检测到 Turnstile")
                        
                        # 深度广告监测与等待
                        log("🎬 监测广告播放中...")
                        start_wait = time.time()
                        while time.time() - start_wait < 90:
                            # 模拟真人活跃，防止广告暂停
                            driver.execute_script("window.dispatchEvent(new Event('mousemove'));")
                            
                            # 检查是否有广告弹窗需要关闭
                            try:
                                driver.execute_script("""
                                    var closeBtns = document.querySelectorAll('[aria-label="Close"], .modal-close');
                                    for(var i=0; i<closeBtns.length; i++) {
                                        if(closeBtns[i].offsetParent !== null) closeBtns[i].click();
                                    }
                                    // 额外: 文本匹配 Close 按钮
                                    var allBtns2 = document.querySelectorAll('button');
                                    for(var j=0; j<allBtns2.length; j++) {
                                        if(allBtns2[j].innerText.indexOf('Close') !== -1 && allBtns2[j].offsetParent !== null) {
                                            allBtns2[j].click();
                                        }
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
                            log("⏳ 续期成功，进入 5 分钟强制冷却期 (310秒)...")
                            time.sleep(310)
                            driver.refresh(); time.sleep(10)
                        else:
                            log(f"❌ 第 {current_round} 轮失败，时间未增加")
                            # 失败时也检查一下是否是因为已经进入了冷却
                            try:
                                page_text = driver.execute_script("return document.body.innerText")
                                if "cd" in page_text:
                                    log("⚠️ 检测到已处于冷却状态，等待 310 秒...")
                                    time.sleep(310); driver.refresh(); time.sleep(10)
                            except: pass
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
