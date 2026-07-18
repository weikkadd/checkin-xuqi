const fs = require('fs');
const c = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py', 'utf8');
const lines = c.split('\n');

// 找到所有仍有问题的 execute_script(f"...) 行
for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes('execute_script(f"') && line.includes('function()')) {
        console.log(`Line ${i+1}: ${line.trim()}`);
        
        // 检查是否已有 {{ }} 转义
        if (line.includes('{{') && line.includes('}}')) {
            console.log('  → Already has {{ }} escape, should be OK');
        } else {
            console.log('  → NEEDS FIX: has { } but no {{ }} escape');
        }
    }
}
