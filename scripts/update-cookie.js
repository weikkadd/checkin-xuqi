/**
 * 交互式更新任务 Cookie
 * 用法: node scripts/update-cookie.js
 *
 * 运行后会提示你输入 taskId 和新的 Cookie 内容,
 * 直接粘贴 Cookie 即可更新数据库, 不需要打开前端面板
 */

require('dotenv').config();
const mysql = require('mysql2/promise');
const readline = require('readline');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function ask(question) {
  return new Promise(resolve => rl.question(question, resolve));
}

(async () => {
  console.log('=== 更新任务 Cookie ===\n');

  // 1. 显示所有任务
  const pool = mysql.createPool({
    uri: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    connectionLimit: 1,
  });

  const [tasks] = await pool.query('SELECT id, name, url, LENGTH(cookies) as cookie_len FROM tasks ORDER BY id');
  console.log('当前任务列表:');
  for (const t of tasks) {
    console.log(`  [${t.id}] ${t.name}  Cookie长度:${t.cookie_len || 0}  ${t.url.substring(0, 60)}`);
  }
  console.log('');

  // 2. 选任务
  const taskIdStr = await ask('请输入要更新 Cookie 的任务 ID: ');
  const taskId = parseInt(taskIdStr, 10);
  if (!taskId) {
    console.log('❌ 任务 ID 无效');
    rl.close();
    await pool.end();
    process.exit(1);
  }

  // 3. 输入 Cookie
  console.log('\n请粘贴新的 Cookie 内容 (一行, 格式: name1=value1; name2=value2; ...)');
  console.log('粘贴完后按回车键:');
  const cookie = (await ask('> ')).trim();

  if (!cookie) {
    console.log('❌ Cookie 不能为空');
    rl.close();
    await pool.end();
    process.exit(1);
  }

  console.log(`\nCookie 长度: ${cookie.length}`);
  console.log(`包含分号数: ${(cookie.match(/;/g) || []).length}`);
  console.log(`前 100 字符: ${cookie.substring(0, 100)}...`);

  // 4. 确认
  const confirm = await ask('\n确认更新? (y/n): ');
  if (confirm.toLowerCase() !== 'y') {
    console.log('已取消');
    rl.close();
    await pool.end();
    process.exit(0);
  }

  // 5. 更新数据库
  const [result] = await pool.query('UPDATE tasks SET cookies = ? WHERE id = ?', [cookie, taskId]);
  console.log(`\n✅ 更新成功! 影响 ${result.affectedRows} 行`);

  // 6. 验证
  const [updated] = await pool.query('SELECT id, name, LENGTH(cookies) as len FROM tasks WHERE id = ?', [taskId]);
  console.log(`任务 [${updated[0].id}] ${updated[0].name} Cookie 长度: ${updated[0].len}`);

  rl.close();
  await pool.end();
})().catch(e => {
  console.error('❌ 异常:', e.message);
  process.exit(1);
});
