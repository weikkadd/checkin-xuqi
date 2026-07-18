const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 删除重复的行
const badLine = '                    if time_matches:\n                        log(f"🔍 页面中发现的时间: {time_matches[:3]}")\n';
const idx = content.indexOf(badLine, content.indexOf('if time_matches:') + 100);
if (idx > -1) {
    content = content.substring(0, idx) + content.substring(idx + badLine.length);
    console.log('✅ Removed duplicate lines at index', idx);
} else {
    console.log('❌ Duplicate not found by exact match');
    // Fallback: find and remove the second occurrence
    const lines = content.split('\n');
    let foundFirst = false;
    let dupStart = -1;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('if time_matches:')) {
            if (foundFirst) {
                dupStart = i;
                break;
            }
            foundFirst = true;
        }
    }
    if (dupStart > 0) {
        // Remove 2 lines (if + log)
        lines.splice(dupStart, 2);
        content = lines.join('\n');
        console.log('✅ Removed duplicate lines at line', dupStart + 1);
    }
}

fs.writeFileSync(path, content, 'utf8');
