const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');
content = content.replace(/\r\n/g, '\n');

const oldMsg = `msg = f"""🎮 Gaming4Free Pro

🖥服务器:
{server_name}

⏰时间:
{now_str()}

📊状态:
{result}

⏱剩余:
{expiry}

⚙️模式:
Renew-Pro v8
"""`;

const newMsg = `msg = f"""🎮 Gaming4Free Pro
🖥服务器: {server_name}
⏰时间: {now_str()}
📊状态: {result}
⏱剩余: {expiry}
⚙️模式: Renew-Pro v10
"""`;

if (content.includes(oldMsg)) {
    content = content.replace(oldMsg, newMsg);
    fs.writeFileSync(path, content, 'utf8');
    console.log('✅ Fixed TG notification format');
} else {
    console.log('oldMsg not found, searching...');
    const idx = content.indexOf('🎮 Gaming4Free Pro');
    if (idx >= 0) {
        console.log('Context:', JSON.stringify(content.substring(idx, idx + 300)));
    }
}
