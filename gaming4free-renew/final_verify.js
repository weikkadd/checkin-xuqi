const fs = require('fs');
const c = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py', 'utf8');

// 检查是否还有问题
const hasBadFString = c.includes('execute_script(f"') && c.includes('function()');
const hasTripleFString = c.includes('execute_script(f"""');

console.log('Has bad single-line f-string:', hasBadFString);
console.log('Has triple-quote f-string:', hasTripleFString);

// 检查修复后的行
const lines = c.split('\n');
for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('.format(') && lines[i].includes('execute_script')) {
        console.log(`\nLine ${i+1}: ${lines[i].trim().substring(0, 100)}`);
    }
}
