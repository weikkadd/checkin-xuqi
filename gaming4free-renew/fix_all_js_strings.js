const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 问题行：find_component_id_by_selector 中使用 f-string 包裹 JS 代码
// 需要将所有 execute_script 中使用 f-string 且包含 JS 大括号的地方都修复

// 方案：将所有 f-string JS 查询改为 .format() 或字符串拼接

// 1. find_component_id_by_selector - 使用 .format()
const oldFindComponent = `def find_component_id_by_selector(sb, selector):
    """根据选择器寻找 wire:id"""
    try:
        return sb.execute_script(f"""
            return (function() {
                let el=document.querySelector('{selector}');
                if(!el) return null;
                let comp=el.closest('[wire\\\\\\\\:id]');
                return comp?comp.getAttribute('wire:id'):null;
            })();
        """)
    except Exception: return None`;

const newFindComponent = `def find_component_id_by_selector(sb, selector):
    """根据选择器寻找 wire:id"""
    try:
        return sb.execute_script(
            "return (function() { " +
            "let el=document.querySelector(arguments[0]); " +
            "if(!el) return null; " +
            "let comp=el.closest('[wire\\\\:id]'); " +
            "return comp?comp.getAttribute('wire:id'):null; " +
            "})();"
            , selector
        )
    except Exception: return None`;

if (content.includes(oldFindComponent)) {
    content = content.replace(oldFindComponent, newFindComponent);
    console.log('✅ Fixed find_component_id_by_selector');
} else {
    console.log('⚠️ find_component_id_by_selector pattern not found exactly, trying line by line');
    
    // 逐行查找并修复
    const lines = content.split('\n');
    let inFunc = false;
    let funcStart = -1;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('def find_component_id_by_selector')) {
            inFunc = true;
            funcStart = i;
        } else if (inFunc && lines[i].startsWith('def ') && i > funcStart) {
            inFunc = false;
        }
        
        if (inFunc && lines[i].includes('execute_script(f"""')) {
            console.log(`Found f-string execute_script at line ${i+1}: ${lines[i].trim()}`);
            // 找到这个函数中的 f-string 块，替换为普通字符串 + 参数传递
            // 从 execute_script(f""" 到 """) 之间的内容
            let jsBlock = '';
            let endLine = i;
            for (let j = i; j < lines.length; j++) {
                if (lines[j].includes('""")') && j > i) {
                    endLine = j;
                    break;
                }
                jsBlock += lines[j] + '\n';
            }
            console.log('JS Block:', jsBlock.substring(0, 200));
            
            // 替换为不带 f-string 的版本，使用 sb.execute_script(js, arg) 传参
            const newLines = [
                `        return sb.execute_script(`,
                `            "return (function() { " +`,
                `            "let el=document.querySelector(arguments[0]); " +`,
                `            "if(!el) return null; " +`,
                `            "let comp=el.closest('[wire\\\\:id]'); " +`,
                `            "return comp?comp.getAttribute('wire:id'):null; " +`,
                `            "})();"`,
                `            , selector`,
                `        )`
            ];
            
            // 替换从 i 到 endLine 的行
            lines.splice(i, endLine - i + 1, ...newLines);
            console.log(`✅ Replaced lines ${i+1}-${endLine+1}`);
            break;
        }
    }
    content = lines.join('\n');
}

// 2. close_modals 中的 execute_script(f"...")
// 查找并修复
const closeModalOld = `if sb.execute_script(f"(function(){{ return !!document.querySelector('{sel}'); }})()"):`;
const closeModalNew = `if sb.execute_script("return !!document.querySelector(arguments[0]);", sel):`;

if (content.includes(closeModalOld)) {
    content = content.replace(closeModalOld, closeModalNew);
    console.log('✅ Fixed close_modals querySelector');
} else {
    console.log('⚠️ close_modals pattern not found');
}

fs.writeFileSync(path, content, 'utf8');
console.log('\n✅ All fixes applied');
