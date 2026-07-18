const fs = require('fs');
const c = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py', 'utf8');

console.log('Has f-string execute_script:', c.includes('execute_script(f"'));
console.log('Has find_component:', c.includes('find_component_id_by_selector'));

const idx = c.indexOf('find_component_id_by_selector');
if (idx >= 0) {
    console.log('\n--- find_component_id_by_selector ---');
    console.log(c.substring(idx, idx + 500));
}

// 检查是否还有 f-string 中包含 { 的情况
const lines = c.split('\n');
for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('execute_script(f"') && lines[i].includes('{')) {
        console.log(`\n⚠️ Line ${i+1} still has f-string with {:`);
        console.log(lines[i].trim());
    }
    if (lines[i].includes('execute_script(f"""') && lines[i].includes('{')) {
        console.log(`\n⚠️ Line ${i+1} still has f-string triple-quote with {:`);
        console.log(lines[i].trim());
    }
}
