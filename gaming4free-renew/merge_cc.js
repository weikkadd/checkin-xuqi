const fs = require('fs');
const path = 'C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py';
let content = fs.readFileSync(path, 'utf8');

// Extract the full check_button_cooldown from backup
const backup = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew_backup.py', 'utf8');
const backupLines = backup.split('\n');

let ccStart = -1, ccEnd = -1;
for (let i = 0; i < backupLines.length; i++) {
    if (backupLines[i].includes('def check_button_cooldown(')) {
        ccStart = i;
    } else if (ccStart >= 0 && backupLines[i].includes('def ') && i > ccStart) {
        ccEnd = i;
        break;
    }
}
if (ccStart < 0 || ccEnd < 0) {
    console.log('Could not extract check_button_cooldown from backup');
    process.exit(1);
}

const oldCC = backupLines.slice(ccStart, ccEnd).join('\n');
console.log('=== Old check_button_cooldown from backup ===');
console.log(oldCC.substring(0, 500));
console.log('...');
console.log(`Total lines: ${ccEnd - ccStart}`);

// Find and replace in renew.py
const lines = content.split('\n');
let newStart = -1, newEnd = -1;
for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('def check_button_cooldown(')) {
        newStart = i;
    } else if (newStart >= 0 && lines[i].includes('def ') && i > newStart) {
        newEnd = i;
        break;
    }
}

if (newStart < 0 || newEnd < 0) {
    console.log('Could not find check_button_cooldown in renew.py');
    process.exit(1);
}

console.log(`\nReplacing lines ${newStart+1}-${newEnd} in renew.py`);
lines.splice(newStart, newEnd - newStart, ...oldCC.split('\n'));
content = lines.join('\n');
fs.writeFileSync(path, content, 'utf8');
console.log('✅ Replaced check_button_cooldown');
