const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');
content = content.replace(/\r\n/g, '\n');

const idx = content.indexOf('# === 进入广告观看流程 ===');
if (idx < 0) { console.log('not found'); process.exit(1); }

// Find the end - look for "if account_finished:" or "except RuntimeError"
const afterIdx = content.substring(idx + 30);
const linesAfter = afterIdx.split('\n');
let endOffset = 0;
for (let i = 0; i < linesAfter.length; i++) {
    const line = linesAfter[i];
    // Stop at the next major block
    if (line.startsWith('                if account_finished:') ||
        line.startsWith('            except RuntimeError') ||
        line.startsWith('            except Exception')) {
        endOffset = i;
        break;
    }
}
if (endOffset === 0) endOffset = linesAfter.length;

const oldBlock = content.substring(idx, idx + 30 + endOffset);
console.log('Old block length:', oldBlock.length);
console.log('Old block preview:', oldBlock.substring(0, 200));

const newBlock = `# === 等待 Turnstile 验证通过后，进入冷却循环 ===
                    log("⏳ 等待 Turnstile 验证通过...")
                    time.sleep(5)
                    
                    # === 循环点击 +90 min 直到达到 48h cap ===
                    MAX_CAP_SECONDS = 48 * 3600
                    RENEW_RETRIES = 10
                    
                    for renew_round in range(RENEW_RETRIES):
                        lt, ls = get_remaining_time(sb)
                        if ls >= MAX_CAP_SECONDS - 60:
                            log(f"✅ 已达到 48h cap ({lt})，停止续期")
                            send_tg("✅ 已达48h上限", server_name, lt)
                            account_finished = True
                            break
                        
                        cooldown_info = check_button_cooldown(sb)
                        if cooldown_info and cooldown_info.get('cooldown'):
                            remaining = cooldown_info.get('remaining', 0)
                            log(f"⏳ 按钮冷却中，剩余 {remaining}秒，等待...")
                            waited = 0
                            while waited < remaining and waited < 600:
                                time.sleep(min(10, remaining - waited))
                                waited += 10
                                cooldown_info = check_button_cooldown(sb)
                                if not (cooldown_info and cooldown_info.get('cooldown')):
                                    break
                            lt, ls = get_remaining_time(sb)
                            if ls >= MAX_CAP_SECONDS - 60:
                                log(f"✅ 已达到 48h cap ({lt})，停止续期")
                                send_tg("✅ 已达48h上限", server_name, lt)
                                account_finished = True
                                break
                            log("🖱️ 冷却结束，点击 +90 min...")
                        else:
                            log("🖱️ 点击 +90 min...")
                        
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
                                log("🛡️ 检测到 Turnstile，处理验证...")
                                try:
                                    sb.uc_gui_click_captcha()
                                    time.sleep(3)
                                except:
                                    pass
                                break
                        
                        time.sleep(5)
                        lt2, ls2 = get_remaining_time(sb)
                        if ls2 > ls + 30:
                            log(f"✅ 续期成功！时间从 {lt} 变为 {lt2}")
                            before_secs = ls2
                            before_text = lt2
                            break
                        else:
                            log(f"⚠️ 续期可能未成功，当前时间: {lt2}")
                    
                    final_text, final_secs = get_remaining_time(sb)
                    if final_secs >= before_secs + 3000 or final_secs >= 3600:
                        log(f"✅ Pro续期成功: {final_text}")
                        send_tg("✅ Pro续期成功", server_name, final_text)
                    else:
                        log(f"⚠️ 续期结果: {final_text}")
                        send_tg(f"⚠️ 续期完成: {final_text}", server_name, final_text)
                    account_finished = True`;

content = content.replace(oldBlock, newBlock);
fs.writeFileSync(path, content, 'utf8');
console.log('✅ Replaced flow');
