const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');
content = content.replace(/\r\n/g, '\n');

// 找到广告流程那段，替换为简单的冷却等待逻辑
const oldFlow = `                    # === 进入广告观看流程 ===
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
                    break`;

const newFlow = `                    # === 等待 Turnstile 验证通过后，进入冷却循环 ===
                    log("⏳ 等待 Turnstile 验证通过...")
                    time.sleep(5)  # 给页面一点时间处理验证
                    
                    # === 循环点击 +90 min 直到达到 48h cap ===
                    MAX_CAP_SECONDS = 48 * 3600  # 48小时
                    RENEW_RETRIES = 10  # 每轮最多重试10次
                    
                    for renew_round in range(RENEW_RETRIES):
                        # 检查是否已达到 48h cap
                        lt, ls = get_remaining_time(sb)
                        if ls >= MAX_CAP_SECONDS - 60:
                            log(f"✅ 已达到 48h cap ({lt})，停止续期")
                            send_tg("✅ 已达48h上限", server_name, lt)
                            account_finished = True
                            break
                        
                        # 检查按钮冷却
                        cooldown_info = check_button_cooldown(sb)
                        if cooldown_info and cooldown_info.get('cooldown'):
                            remaining = cooldown_info.get('remaining', 0)
                            log(f"⏳ 按钮冷却中，剩余 {remaining}秒，等待...")
                            # 等待冷却结束
                            waited = 0
                            while waited < remaining and waited < 600:
                                time.sleep(min(10, remaining - waited))
                                waited += 10
                                # 重新检查冷却
                                cooldown_info = check_button_cooldown(sb)
                                if not (cooldown_info and cooldown_info.get('cooldown')):
                                    break
                            # 冷却后重新检查时间
                            lt, ls = get_remaining_time(sb)
                            if ls >= MAX_CAP_SECONDS - 60:
                                log(f"✅ 已达到 48h cap ({lt})，停止续期")
                                send_tg("✅ 已达48h上限", server_name, lt)
                                account_finished = True
                                break
                            # 冷却后点击按钮
                            log("🖱️ 冷却结束，点击 +90 min...")
                        else:
                            log("🖱️ 点击 +90 min...")
                        
                        # 点击 +90 min 按钮
                        click_result = sb.execute_script("""
                            var btns = document.querySelectorAll('button');
                            for (var i = 0; i < btns.length; i++) {
                                if ((btns[i].textContent || '').indexOf('90') !== -1) {
                                    btns[i].scrollIntoView({block: 'center'});
                                    btns[i].removeAttribute('disabled');
                                    btns[i].style.cssText += '; pointer-events:auto !important;';
                                    btns[i].click();
                                    return 'clicked:' + btns[i].textContent.trim();
                                }
                            }
                            return 'not-found';
                        """)
                        log(f"🎯 点击结果: {click_result}")
                        
                        # 等待 Turnstile 出现并处理
                        turnstile_found = False
                        for wi in range(30):
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
                                turnstile_found = True
                                log("🛡️ 检测到 Turnstile，处理验证...")
                                try:
                                    sb.uc_gui_click_captcha()
                                    time.sleep(3)
                                except:
                                    pass
                                break
                        
                        if not turnstile_found:
                            log("ℹ️ 未检测到 Turnstile，继续等待...")
                        
                        # 等待页面响应
                        time.sleep(5)
                        
                        # 检查时间是否增加
                        lt2, ls2 = get_remaining_time(sb)
                        if ls2 > ls + 30:
                            log(f"✅ 续期成功！时间从 {lt} 变为 {lt2}")
                            before_secs = ls2
                            before_text = lt2
                            break
                        else:
                            log(f"⚠️ 续期可能未成功，当前时间: {lt2}")
                    
                    # === 最终确认 ===
                    final_text, final_secs = get_remaining_time(sb)
                    if final_secs >= before_secs + 3000 or final_secs >= 3600:
                        log(f"✅ Pro续期成功: {final_text}")
                        send_tg("✅ Pro续期成功", server_name, final_text)
                        account_finished = True
                    else:
                        log(f"⚠️ 续期结果: {final_text}")
                        send_tg(f"⚠️ 续期完成: {final_text}", server_name, final_text)
                        account_finished = True`;

if content.replace(oldFlow, newFlow) == content:
    # Try with normalized line endings
    oldFlowNorm = oldFlow.replace(/\r\n/g, '\n');
    if (content.includes(oldFlowNorm)) {
        content = content.replace(oldFlowNorm, newFlow);
        console.log('✅ Replaced flow (normalized)');
    } else {
        console.log('Pattern not found, searching...');
        const idx = content.indexOf('# === 进入广告观看流程 ===');
        if (idx >= 0) {
            console.log('Found at:', idx);
            console.log('Context:', JSON.stringify(content.substring(idx, idx + 200)));
        }
    }
} else {
    content = content.replace(oldFlow, newFlow);
    console.log('✅ Replaced flow');
}

fs.writeFileSync(path, content, 'utf8');
