/**
 * gaming4free 页面诊断脚本
 * 用法: node scripts/diag.js
 *
 * 会做这些事:
 *  1. 从数据库读取 id=1 任务的配置 (URL, Cookie, renewButtonText)
 *  2. 用 Playwright 打开页面, 注入 Cookie
 *  3. 等 12 秒让页面加载完
 *  4. 输出页面前 1500 字文本
 *  5. 输出所有可点击元素 (button/a/[role=button]) 的文字、disabled 状态、class
 *  6. 保存截图到 /tmp/diag-screenshot.jpg
 *  7. 尝试用 3 种方法点击 +90 min 按钮, 输出哪种方法成功
 *  8. 等 5 秒后再次输出页面文本 (看时间是否增加)
 */

const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
chromium.use(StealthPlugin());

require('dotenv').config();
const mysql = require('mysql2/promise');
const fs = require('fs');

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  console.log('=== [1/8] 从数据库读取任务 ===');
  const pool = mysql.createPool({
    uri: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    connectionLimit: 1,
  });
  const [rows] = await pool.query('SELECT * FROM tasks WHERE id = 1');
  await pool.end();

  if (!rows.length) {
    console.log('❌ 任务 id=1 不存在');
    process.exit(1);
  }
  const task = rows[0];
  console.log('任务名:', task.name);
  console.log('URL:', task.url);
  console.log('按钮文字:', JSON.stringify(task.renewButtonText));
  console.log('Cookie 长度:', task.cookies ? task.cookies.length : 0);

  console.log('\n=== [2/8] 启动浏览器 ===');
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
    locale: 'zh-CN',
  });
  await ctx.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });

  // 注入 Cookie
  if (task.cookies) {
    let cookieStr = task.cookies;
    if (cookieStr.trim().startsWith('[')) {
      try {
        const arr = JSON.parse(cookieStr);
        cookieStr = arr.map(c => `${c.name}=${c.value}`).join('; ');
      } catch {}
    }
    const url = new URL(task.url);
    const cookies = cookieStr.split(';').filter(s => s.trim()).map(c => {
      const idx = c.indexOf('=');
      const name = c.substring(0, idx).trim();
      const value = c.substring(idx + 1).trim();
      return { name, value, domain: '.' + url.hostname.split('.').slice(-2).join('.'), path: '/' };
    });
    await ctx.addCookies(cookies);
    console.log(`✅ 注入 ${cookies.length} 个 Cookie (domain: .${url.hostname.split('.').slice(-2).join('.')})`);
  }

  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);

  console.log('\n=== [3/8] 打开页面 ===');
  try {
    await page.goto(task.url, { waitUntil: 'load', timeout: 60000 });
    console.log('✅ 页面加载完成');
  } catch (e) {
    console.log('⚠️ page.goto 异常:', e.message);
  }
  await sleep(12000);

  // 检测 CF
  const isCF = await page.evaluate(() => {
    const t = document.body.innerText || '';
    return t.includes('Just a moment') || t.includes('请验证你是真人') || t.includes('Verify you are human');
  }).catch(() => false);
  console.log('CF 验证页:', isCF);

  console.log('\n=== [4/8] 页面文本（前 1500 字）===');
  const text1 = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log(text1.substring(0, 1500));

  console.log('\n=== [5/8] 页面所有可点击元素 ===');
  const btns = await page.evaluate(() => {
    return [...document.querySelectorAll('button, a, [role=button], [onclick], .btn, .button, input[type=button], input[type=submit]')]
      .map(b => ({
        tag: b.tagName,
        text: (b.innerText || b.textContent || b.value || '').trim().substring(0, 80),
        disabled: b.disabled || false,
        ariaDisabled: b.getAttribute('aria-disabled'),
        classes: (b.className || '').toString().substring(0, 120),
        visible: b.offsetParent !== null,
      }))
      .filter(b => b.text || b.tag !== 'A');
  }).catch(() => []);
  console.log(JSON.stringify(btns, null, 2));

  console.log('\n=== [6/8] 保存截图 ===');
  const ss = await page.screenshot({ fullPage: false, type: 'jpeg', quality: 60 });
  fs.writeFileSync('/tmp/diag-screenshot.jpg', ss);
  console.log('截图已保存: /tmp/diag-screenshot.jpg');

  // 提取点击前的剩余时间
  const beforeText = text1;
  const beforeMatch = beforeText.match(/(\d{1,2}:\d{2}:\d{2})/);
  console.log('\n=== [7/8] 尝试点击 +90 min 按钮（3 种方法）===');
  console.log('点击前页面首个时间:', beforeMatch ? beforeMatch[1] : '未找到');

  const buttonText = (task.renewButtonText || '+90 min').trim();
  let clicked = false;
  let clickMethod = '';

  // 方法 1: getByRole
  try {
    const locator = page.getByRole('button', { name: buttonText, exact: false });
    if (await locator.count() > 0) {
      console.log(`方法 1 (getByRole): 找到 ${await locator.count()} 个匹配`);
      await locator.first().click({ timeout: 5000 });
      clicked = true;
      clickMethod = 'getByRole';
      console.log('✅ 方法 1 点击成功');
    } else {
      console.log('方法 1 (getByRole): 没找到');
    }
  } catch (e) {
    console.log('方法 1 (getByRole) 异常:', e.message);
  }

  // 方法 2: text= 选择器
  if (!clicked) {
    try {
      const locator = page.locator(`text="${buttonText}"`).first();
      if (await locator.isVisible().catch(() => false)) {
        await locator.click({ timeout: 5000 });
        clicked = true;
        clickMethod = 'text=';
        console.log('✅ 方法 2 点击成功');
      } else {
        console.log('方法 2 (text=): 不可见');
      }
    } catch (e) {
      console.log('方法 2 (text=) 异常:', e.message);
    }
  }

  // 方法 3: evaluate 遍历
  if (!clicked) {
    try {
      const result = await page.evaluate((target) => {
        const norm = target.toLowerCase().replace(/\s+/g, '');
        const clickables = document.querySelectorAll('button, a, [role=button], [onclick]');
        for (const el of clickables) {
          const text = ((el.innerText || el.textContent || '')).toLowerCase().replace(/\s+/g, '');
          if (text && text.includes(norm)) {
            const btn = el;
            if (btn.disabled) continue;
            (el).click();
            return text;
          }
        }
        // 模糊匹配: 包含 +90 或 90min
        for (const el of clickables) {
          const text = ((el.innerText || el.textContent || '')).toLowerCase();
          if (text.includes('+90') || text.includes('90 min') || text.includes('90min') || text.includes('add 90')) {
            if (el.disabled) continue;
            (el).click();
            return 'fuzzy:' + text;
          }
        }
        return null;
      }, buttonText);
      if (result) {
        clicked = true;
        clickMethod = 'evaluate';
        console.log('✅ 方法 3 点击成功, 匹配到:', result);
      } else {
        console.log('方法 3 (evaluate): 没找到任何包含 +90 的按钮');
      }
    } catch (e) {
      console.log('方法 3 (evaluate) 异常:', e.message);
    }
  }

  if (!clicked) {
    console.log('\n❌ 三种方法都没点击成功 - 按钮可能不存在或文字不匹配');
  }

  // 等页面响应
  console.log('\n=== [8/8] 等 8 秒后再次读取页面 ===');
  await sleep(8000);

  const text2 = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('点击后页面文本（前 800 字）:');
  console.log(text2.substring(0, 800));

  const afterMatch = text2.match(/(\d{1,2}:\d{2}:\d{2})/);
  console.log('\n点击后页面首个时间:', afterMatch ? afterMatch[1] : '未找到');

  // 时间对比
  if (beforeMatch && afterMatch) {
    const [bh, bm] = beforeMatch[1].split(':').map(Number);
    const [ah, am] = afterMatch[1].split(':').map(Number);
    const beforeMin = bh * 60 + bm;
    const afterMin = ah * 60 + am;
    const diff = afterMin - beforeMin;
    console.log(`\n时间变化: ${beforeMatch[1]} → ${afterMatch[1]} (${diff > 0 ? '+' : ''}${diff} 分钟)`);
    if (diff > 0) {
      console.log('✅ 时间增加了! 点击生效了!');
    } else if (diff === 0) {
      console.log('⚠️ 时间没变 - 点击可能没生效, 或页面需要更多时间响应');
    } else {
      console.log('⚠️ 时间减少了 - 可能匹配到的是冷却倒计时, 不是剩余时间');
    }
  }

  // 保存点击后截图
  const ss2 = await page.screenshot({ fullPage: false, type: 'jpeg', quality: 60 });
  fs.writeFileSync('/tmp/diag-screenshot-after.jpg', ss2);
  console.log('\n点击后截图已保存: /tmp/diag-screenshot-after.jpg');

  // ============================================
  // 新增: 尝试用新的 clickButtonOnce 逻辑点击 + 验证
  // ============================================
  console.log('\n=== [额外] 尝试用真实鼠标点击 (hover + click + 鼠标坐标) ===');
  
  // 方法 A: 用 Playwright 真实鼠标点击 class rt-btn-free
  try {
    const locator = page.locator('button.rt-btn-free, .rt-btn-free').first();
    if (await locator.isVisible().catch(() => false)) {
      console.log('找到 rt-btn-free 按钮, 用真实鼠标点击...');
      await locator.hover({ timeout: 3000 });
      await sleep(500);
      
      // 记录点击前时间
      const beforeText = await page.evaluate(() => document.body.innerText).catch(() => '');
      const beforeTime = beforeText.match(/(\d{1,2}:\d{2}:\d{2})/);
      console.log('真实鼠标点击前时间:', beforeTime ? beforeTime[1] : '未找到');
      
      // 真实鼠标点击
      await locator.click({ timeout: 5000 });
      console.log('✅ Playwright click() 执行完成');
      
      // 等 10 秒
      await sleep(10000);
      
      // 检查时间变化
      const afterText2 = await page.evaluate(() => document.body.innerText).catch(() => '');
      const afterTime2 = afterText2.match(/(\d{1,2}:\d{2}:\d{2})/);
      console.log('真实鼠标点击后时间:', afterTime2 ? afterTime2[1] : '未找到');
      
      if (beforeTime && afterTime2) {
        const [bh2, bm2] = beforeTime[1].split(':').map(Number);
        const [ah2, am2] = afterTime2[1].split(':').map(Number);
        const diff2 = (ah2 * 60 + am2) - (bh2 * 60 + bm2);
        console.log(`时间变化: ${diff2 > 0 ? '+' : ''}${diff2} 分钟`);
        if (diff2 > 0) {
          console.log('🎉🎉🎉 真实鼠标点击生效了! 时间增加了', diff2, '分钟!');
        } else {
          console.log('❌ 真实鼠标点击也没生效 - 可能需要其他方式');
          
          // 输出按钮的 HTML 看看
          const btnHtml = await page.evaluate(() => {
            const btn = document.querySelector('button.rt-btn-free, .rt-btn-free');
            return btn ? btn.outerHTML : 'not found';
          }).catch(() => 'error');
          console.log('\n按钮 HTML:');
          console.log(btnHtml);
          
          // 检查按钮的 onclick 监听器
          const btnInfo = await page.evaluate(() => {
            const btn = document.querySelector('button.rt-btn-free, .rt-btn-free');
            if (!btn) return null;
            // 检查是否有 React 事件
            const reactKey = Object.keys(btn).find(k => k.startsWith('__reactProps') || k.startsWith('__reactEventHandlers'));
            return {
              tagName: btn.tagName,
              type: btn.type,
              formAction: btn.formAction,
              onclick: btn.onclick ? btn.onclick.toString() : null,
              reactKey: reactKey,
              parentTag: btn.parentElement?.tagName,
              parentClass: btn.parentElement?.className,
            };
          }).catch(() => null);
          console.log('\n按钮信息:');
          console.log(JSON.stringify(btnInfo, null, 2));
        }
      }
    } else {
      console.log('rt-btn-free 按钮不可见');
    }
  } catch (e) {
    console.log('真实鼠标点击异常:', e.message);
  }

  // 保存最终截图
  const ss3 = await page.screenshot({ fullPage: false, type: 'jpeg', quality: 60 });
  fs.writeFileSync('/tmp/diag-screenshot-final.jpg', ss3);
  console.log('\n最终截图已保存: /tmp/diag-screenshot-final.jpg');

  await browser.close();
  console.log('\n=== 诊断完成 ===');
  console.log('点击方法:', clickMethod || '未点击成功');
})().catch(e => {
  console.error('❌ 诊断脚本异常:', e.message);
  console.error(e.stack);
  process.exit(1);
});
