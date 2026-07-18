const fs = require('fs');
const c = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py', 'utf8');
const lines = c.split('\n');
console.log('Total lines:', lines.length);
for (let i = Math.max(0, 715); i < Math.min(lines.length, 730); i++) {
    console.log((i + 1) + ': ' + lines[i]);
}
