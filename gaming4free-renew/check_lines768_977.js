const fs = require('fs');
const c = fs.readFileSync('C:\\Users\\ASUS\\Documents\\AgnesCode\\checkin-xuqi\\gaming4free-renew\\renew.py', 'utf8');
const lines = c.split('\n');

// Line 768
console.log('=== Line 768 area ===');
for (let i = 765; i < 780 && i < lines.length; i++) {
    console.log((i+1) + ': ' + lines[i]);
}

console.log('\n=== Line 977 area ===');
for (let i = 974; i < 990 && i < lines.length; i++) {
    console.log((i+1) + ': ' + lines[i]);
}
