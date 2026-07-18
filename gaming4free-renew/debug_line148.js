const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
const content = fs.readFileSync(path, 'utf8');
const lines = content.split('\n');
console.log('Total lines:', lines.length);
for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes("querySelector('{sel}')")) {
        console.log(`Line ${i + 1}: ${lines[i]}`);
        // Show context
        for (let j = Math.max(0, i - 2); j <= Math.min(lines.length - 1, i + 2); j++) {
            console.log(`  ${j + 1}: ${lines[j]}`);
        }
    }
}
