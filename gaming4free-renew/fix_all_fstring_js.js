const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 修复策略：将 f""" JS 代码块 改为 .format() 或字符串拼接
// 这样 JS 的大括号就只是普通字符，不会与 f-string 冲突

// 1. 修复第 768 行附近的 Livewire 调用 f-string
// 找到从 result = sb.execute_script(f""" 到对应的 """)
const lines = content.split('\n');

let fixed = 0;
let i = 0;
while (i < lines.length) {
    const line = lines[i];
    
    // 匹配 execute_script(f""" 或 execute_script(f"
    if (line.includes('execute_script(f"""')) {
        // 找到这个多行字符串的结束
        let startLine = i;
        let endLine = -1;
        let blockContent = line;
        
        for (let j = i + 1; j < lines.length; j++) {
            blockContent += '\n' + lines[j];
            if (lines[j].includes('""")') || lines[j].includes('""")')) {
                endLine = j;
                break;
            }
        }
        
        if (endLine === -1) {
            i++;
            continue;
        }
        
        const fullBlock = lines.slice(startLine, endLine + 1).join('\n');
        
        // 检查是否包含变量插值
        const hasVarInterpolation = /\{[a-zA-Z_]\w*\}/.test(fullBlock);
        
        if (hasVarInterpolation) {
            // 有变量插值，需要将 JS 的 { } 转义为 {{ }}
            // 同时保留变量插值
            
            // 提取变量名
            const varMatches = fullBlock.match(/\{([a-zA-Z_]\w*)\}/g);
            const varNames = varMatches ? [...new Set(varMatches.map(v => v.slice(1, -1)))] : [];
            
            console.log(`\nFixing lines ${startLine+1}-${endLine+1}, vars: ${varNames.join(', ')}`);
            
            // 构建新的代码：使用 .format() 替代 f-string
            // 将 f"""...""" 改为 """...""".format(...)
            // 并将 JS 的 { 替换为 {{，} 替换为 }}，但保留 {var} 不变
            
            let newBlock = fullBlock;
            
            // 先保护变量插值
            varNames.forEach(v => {
                const placeholder = `__VAR_${v.toUpperCase()}__`;
                newBlock = newBlock.replace(new RegExp(`\\{${v}\\}`, 'g'), placeholder);
            });
            
            // 转义 JS 大括号
            newBlock = newBlock.replace(/\{/g, '{{').replace(/\}/g, '}}');
            
            // 恢复变量插值占位符
            varNames.forEach(v => {
                const placeholder = `__VAR_${v.toUpperCase()}__`;
                newBlock = newBlock.replace(placeholder, `{${v}}`);
            });
            
            // 将 f""" 替换为 """ 并在末尾加 .format(...)
            newBlock = newBlock.replace(/^(\s*)(result = |)sb\.execute_script\(f"""/, `$1$2sb.execute_script("""`);
            newBlock = newBlock.replace(/"""\)/, `""").format(${varNames.join(', ')})`);
            newBlock = newBlock.replace(/"""\s*$/, `""").format(${varNames.join(', ')})`);
            
            lines.splice(startLine, endLine - startLine + 1, newBlock);
            fixed++;
            console.log(`✅ Fixed block at lines ${startLine+1}-${endLine+1}`);
        }
        
        i = endLine + 1;
    } else if (line.includes('execute_script(f"') && !line.includes('execute_script(f"""')) {
        // 单行 f-string，检查是否有 JS 大括号
        const trimmed = line.trim();
        if (trimmed.includes('function') || trimmed.includes('document') || trimmed.includes('return')) {
            // 检查是否已经有 {{ }} 转义
            if (trimmed.includes('{') && !trimmed.includes('{{')) {
                console.log(`\nFixing line ${i+1}: ${trimmed.substring(0, 100)}`);
                
                // 提取变量名
                const varMatches = trimmed.match(/\{([a-zA-Z_]\w*)\}/g);
                const varNames = varMatches ? [...new Set(varMatches.map(v => v.slice(1, -1)))] : [];
                
                if (varNames.length > 0) {
                    // 保护变量，转义 JS 大括号
                    let newLine = trimmed;
                    varNames.forEach(v => {
                        const placeholder = `__VAR_${v.toUpperCase()}__`;
                        newLine = newLine.replace(new RegExp(`\\{${v}\\}`, 'g'), placeholder);
                    });
                    newLine = newLine.replace(/\{/g, '{{').replace(/\}/g, '}}');
                    varNames.forEach(v => {
                        const placeholder = `__VAR_${v.toUpperCase()}__`;
                        newLine = newLine.replace(placeholder, `{${v}}`);
                    });
                    
                    // 将 f"..." 改为 "...".format(...)
                    newLine = newLine.replace(/f"(.*)"$/, '"$1".format(${varNames.join(', ')})');
                    
                    lines[i] = line.replace(trimmed, newLine);
                    fixed++;
                    console.log(`✅ Fixed: ${lines[i].trim().substring(0, 100)}`);
                }
            }
        }
        i++;
    } else {
        i++;
    }
}

if (fixed > 0) {
    content = lines.join('\n');
    fs.writeFileSync(path, content, 'utf8');
    console.log(`\n✅ Total fixed: ${fixed} locations`);
} else {
    console.log('\n❌ No fixes needed');
}
