const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 修复：page_text 可能为 None，需要先检查
const oldCode = `                    page_text = sb.execute_script("(function(){ return document.body?document.body.innerText:''; })()")
                    time_matches = re.findall(r'(\\d{1,2}:\\d{2}:\\d{2})', page_text)`;

const newCode = `                    page_text = sb.execute_script("(function(){ return document.body?document.body.innerText:''; })()")
                    if page_text:
                        time_matches = re.findall(r'(\\d{1,2}:\\d{2}:\\d{2})', page_text)
                        if time_matches:
                            log(f"🔍 页面中发现的时间: {time_matches[:3]}")`;

if (content.includes(oldCode)) {
    content = content.replace(oldCode, newCode);
    fs.writeFileSync(path, content, 'utf8');
    console.log('✅ Fixed: added null check for page_text');
} else {
    console.log('❌ Pattern not found exactly');
    // Try to find partial match
    const idx = content.indexOf('page_text = sb.execute_script');
    if (idx > -1) {
        console.log('Found page_text at:', idx);
        console.log('Context:', content.substring(idx, idx + 300));
    }
}
