const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 查找所有包含 f-string + execute_script + JS 大括号的行
const lines = content.split('\n');
let issues = [];
for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes('execute_script') && line.includes('f"') && line.includes('{') && !line.includes('{{')) {
        issues.push({ lineNum: i + 1, content: line.trim() });
    }
}

console.log(`Found ${issues.length} potential issues:`);
issues.forEach(issue => {
    console.log(`Line ${issue.lineNum}: ${issue.content.substring(0, 120)}`);
});

// 修复所有 f-string 中包含 JS 大括号的问题
// 规则：f"..." 中的 { 如果不是变量引用（即不是 {variable} 格式），需要转义为 {{
// 简单方法：找到所有 execute_script 的 f-string，将 JS 代码块的 { 替换为 {{

// 策略：将所有 execute_script(f"...") 中的独立 { 和 } 替换为 {{ 和 }}
// 但要保留 {variable} 形式的 f-string 插值

// 更精确的方法：逐行修复
let fixed = 0;
for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (!line.includes('execute_script') || !line.includes('f"')) continue;
    
    // 找到 f-string 内容
    const fStart = line.indexOf('f"');
    if (fStart === -1) continue;
    
    // 简单的启发式修复：如果行内有 JS 代码（function, var, let, const, document, return），
    // 且有大括号但不是 {variable} 形式，则转义
    
    // 匹配 JS 代码块中的大括号
    // 例如: f"(function(){ ... })()" -> f"(function(){{ ... }})()"
    // 但保留: f"...{variable}..."
    
    // 使用正则替换：将不属于 f-string 插值的 { 替换为 {{
    // 思路：f-string 中的 {xxx} 是变量，单独的 { 或 } 是 JS 代码需要转义
    
    const original = line;
    
    // 匹配 f"(function(){ ... })()" 模式
    line = line.replace(/f"\(function\(\)\{(?!\w)/g, 'f"(function(){');
    
    // 更通用的方法：找到 f" 内的所有内容，区分变量插值和字面量
    // 由于 Python f-string 中 {{ 表示字面量 {，我们只需要确保 JS 的 { 变成 {{
    
    // 简单而安全的做法：将整个 f-string 中的非变量 { } 替换
    // 变量模式：{word} 或 {word.method()} 或 {word[attr]}
    // 其他 { 都是 JS 代码，需要 {{
    
    // 使用更简单的方法：替换所有在 f" 开头和结尾之间的孤立 {
    // 找到 f" 的起始和结束位置
    const fQuoteStart = line.indexOf('f"', fStart);
    if (fQuoteStart === -1) continue;
    
    // 找到匹配的闭合引号（处理转义）
    let depth = 0;
    let inFString = false;
    let result = '';
    for (let j = fQuoteStart; j < line.length; j++) {
        const ch = line[j];
        const prev = j > 0 ? line[j-1] : '';
        
        if (ch === '"' && prev !== '\\') {
            if (inFString) {
                result += '"';
                break;
            }
            inFString = true;
            result += '"';
            continue;
        }
        
        if (inFString) {
            // 检查是否是 f-string 变量插值 {expr}
            if (ch === '{' && prev !== '\\') {
                // 检查后面是否是字母/数字/下划线（变量名）
                let rest = line.substring(j + 1);
                if (/^\w/.test(rest)) {
                    // 这是变量插值，保持原样
                    result += '{';
                } else {
                    // 这是 JS 代码的大括号，转义
                    result += '{{';
                }
            } else if (ch === '}' && prev !== '\\') {
                // 检查前面是否是变量插值的结束
                let before = line.substring(Math.max(0, j - 20), j);
                if (/\w/.test(before.slice(-1))) {
                    // 变量插值的 }
                    result += '}';
                } else {
                    // JS 代码的 }
                    result += '}}';
                }
            } else {
                result += ch;
            }
        } else {
            result += ch;
        }
    }
    
    // 追加剩余部分
    if (inFString) {
        result += line.substring(j + 1);
    } else {
        result += line.substring(fQuoteStart);
    }
    
    if (result !== line) {
        lines[i] = line.substring(0, fQuoteStart) + result;
        fixed++;
        console.log(`Fixed line ${i + 1}:`);
        console.log(`  OLD: ${original.trim()}`);
        console.log(`  NEW: ${lines[i].trim()}`);
    }
}

if (fixed > 0) {
    content = lines.join('\n');
    fs.writeFileSync(path, content, 'utf8');
    console.log(`\n✅ Fixed ${fixed} lines`);
} else {
    console.log('\n❌ No fixes needed');
}
