const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// 修复两处多余的右括号
// 1. 第 148 行: }})()")) -> }})()")
content = content.replace(
    /text = sb\.execute_script\(f"\(function\(\)\{\{ var el=document\.querySelector\('(\{sel\})'\); return el\?el\.textContent\.trim\(\):\s*''; \}\}\)\(\)"\)\)/g,
    "text = sb.execute_script(f\"(function(){{ var el=document.querySelector('{sel}'); return el?el.textContent.trim():''; }})()\")"
);

// 2. 第 181 行: }})()")) -> }})()")
content = content.replace(
    /if sb\.execute_script\(f"\(function\(\)\{\{ return !!\s*document\.querySelector\('(\{sel\})'\); \}\}\)\(\)"\)\)/g,
    "if sb.execute_script(f\"(function(){{ return !!document.querySelector('{sel}'); }})()\")"
);

fs.writeFileSync(path, content, 'utf8');
console.log('✅ Fixed extra closing parentheses');

// 验证
const lines = content.split('\n');
let found = false;
for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes("querySelector('{sel}')")) {
        console.log(`Line ${i + 1}: ${lines[i].trim()}`);
        found = true;
    }
}
if (!found) console.log('No querySelector lines found');
