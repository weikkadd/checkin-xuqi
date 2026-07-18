const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 修复 f-string 中的 JavaScript 大括号冲突问题
// 原代码：text = sb.execute_script(f"(function(){ var el=document.querySelector('{sel}'); return el?el.textContent.trim():''; })()")
// 问题：f-string 中的 {sel} 和 JS 的 {} 冲突

// 方法1：将 f-string 改为普通字符串 + .format()
// 方法2：使用双大括号 {{ }} 转义 JS 的大括号

// 查找并替换所有类似问题
const patterns = [
    // 策略2中的 CSS 选择器查询
    {
        search: 'text = sb.execute_script(f"(function(){ var el=document.querySelector(\'{sel}\'); return el?el.textContent.trim():\'\'; })()"',
        replace: 'text = sb.execute_script(f"(function(){{ var el=document.querySelector(\'{sel}\'); return el?el.textContent.trim():\'\'; }})()")'
    },
    // close_modals 中的查询
    {
        search: 'if sb.execute_script(f"(function(){ return !!document.querySelector(\'{sel}\'); })()"):',
        replace: 'if sb.execute_script(f"(function(){{ return !!document.querySelector(\'{sel}\'); }})()"):'
    }
];

let fixed = 0;
for (const pattern of patterns) {
    if (content.includes(pattern.search)) {
        content = content.replace(pattern.search, pattern.replace);
        fixed++;
        console.log(`✅ Fixed pattern ${fixed}`);
    }
}

if (fixed > 0) {
    fs.writeFileSync(path, content, 'utf8');
    console.log(`✅ Total fixed: ${fixed} patterns`);
} else {
    console.log('❌ No patterns found to fix');
    // 尝试查找包含 execute_script 和 f-string 的行
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('execute_script') && lines[i].includes('f"') && lines[i].includes('{')) {
            console.log(`Line ${i+1}: ${lines[i].substring(0, 100)}`);
        }
    }
}
