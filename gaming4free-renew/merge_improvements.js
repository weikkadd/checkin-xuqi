const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// Fix 1: Add wait loop for before_secs
const oldBefore = '                    screenshot(sb, "before-login")\n                    before_text, before_secs = get_remaining_time(sb)\n                    log(f"⏱️ 续期前剩余时长: {before_text} ({before_secs}秒)")';
const newBefore = `                    screenshot(sb, "before-login")
                    # 等待页面完全渲染以获取准确的初始时间
                    log("⏳ 等待页面完全渲染以获取初始时间...")
                    before_secs = 0
                    before_text = ""
                    for _wait in range(15):
                        text, secs = get_remaining_time(sb)
                        if secs > 0:
                            before_text, before_secs = text, secs
                            log(f"⏱️ 续期前剩余时长: {before_text} ({before_secs}秒)")
                            break
                        time.sleep(1)
                    else:
                        log(f"⏱️ 续期前剩余时长: {before_text} ({before_secs}秒) - 页面未完全渲染")`;

if (content.includes(oldBefore)) {
    content = content.replace(oldBefore, newBefore);
    console.log('✅ Fixed before_secs wait logic');
} else {
    console.log('⚠️ before_secs pattern not found exactly');
    // Normalize and try again
    content = content.replace(/\r\n/g, '\n');
    if (content.includes(oldBefore.replace(/\r\n/g, '\n'))) {
        content = content.replace(oldBefore.replace(/\r\n/g, '\n'), newBefore);
        console.log('✅ Fixed before_secs wait logic (normalized)');
    } else {
        console.log('Still not found, checking context...');
        const idx = content.indexOf('before-login');
        if (idx >= 0) console.log('Context:', JSON.stringify(content.substring(idx, idx + 300)));
    }
}

// Fix 2: Replace check_button_cooldown with the improved version from backup
const backup = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew_backup.py', 'utf8').replace(/\r\n/g, '\n');
const backupLines = backup.split('\n');
let ccStart = -1, ccEnd = -1;
for (let i = 0; i < backupLines.length; i++) {
    if (backupLines[i].includes('def check_button_cooldown(')) ccStart = i;
    else if (ccStart >= 0 && backupLines[i].includes('def ') && i > ccStart) { ccEnd = i; break; }
}
if (ccStart >= 0 && ccEnd >= 0) {
    const oldCC = backupLines.slice(ccStart, ccEnd).join('\n');
    // Find in current content
    const lines = content.split('\n');
    let ns = -1, ne = -1;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('def check_button_cooldown(')) ns = i;
        else if (ns >= 0 && lines[i].includes('def ') && i > ns) { ne = i; break; }
    }
    if (ns >= 0 && ne >= 0) {
        lines.splice(ns, ne - ns, ...oldCC.split('\n'));
        content = lines.join('\n');
        console.log('✅ Replaced check_button_cooldown with improved version');
    }
}

fs.writeFileSync(path, content, 'utf8');
console.log('\n✅ All fixes applied');
