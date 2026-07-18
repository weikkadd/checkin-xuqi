const fs = require('fs');
const c = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py', 'utf8');

// 查找所有 execute_script 中的 f-string 模式
const lines = c.split('\n');
let issues = [];
for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes('execute_script(f"') || line.includes('execute_script(f"""')) {
        issues.push({ lineNum: i + 1, content: line.trim(), multi: line.includes('"""') });
    }
}

console.log(`Found ${issues.length} execute_script f-string lines:`);
issues.forEach(issue => {
    console.log(`\nLine ${issue.lineNum} (${issue.multi ? 'triple' : 'single'} quote):`);
    console.log(`  ${issue.content.substring(0, 150)}`);
    
    // 检查是否有未转义的大括号
    const hasUnescaped = issue.content.includes('{') && 
                         !issue.content.includes('{{') && 
                         issue.content.includes('function') ||
                         issue.content.includes('document') ||
                         issue.content.includes('return');
    if (hasUnescaped) {
        console.log('  ⚠️ May have unescaped JS braces');
    }
});
