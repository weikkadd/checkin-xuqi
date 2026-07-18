const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 查找问题行：return Nonedef handle_turnstile
const badPattern = 'return Nonedef handle_turnstile';
const goodPattern = 'return None\n\ndef handle_turnstile';

const idx = content.indexOf(badPattern);
if (idx > -1) {
    console.log(`Found bad pattern at char ${idx}`);
    console.log('Context:', JSON.stringify(content.substring(idx, idx + 80)));
    content = content.replace(badPattern, goodPattern);
    fs.writeFileSync(path, content, 'utf8');
    console.log('✅ Fixed: added newline between return None and def handle_turnstile');
} else {
    console.log('❌ Pattern not found, searching for similar...');
    // 查找 return None 后面紧跟 def 的情况
    const regex = /return None(def\s+\w+)/g;
    let match;
    while ((match = regex.exec(content)) !== null) {
        console.log(`Found at ${match.index}: ...${match[0]}...`);
    }
}
