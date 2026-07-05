/**
 * gaming4free 验证弹窗诊断脚本
 * 用法: node scripts/diag-captcha.js
 *
 * 1. 打开页面 + 注入 Cookie
 * 2. 等 12 秒页面加载
 * 3. 用 force: true 强制点击 +90 min 按钮
 * 4. 等 5 秒让验证弹窗出现
 * 5. 输出验证弹窗的完整 HTML
 * 6. 输出所有 iframe (验证码通常在 iframe 里)
 * 7. 输出页面上所有可见文本
 */

const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
chromium.use(StealthPlugin());

require('dotenv').config();
const mysql = require('mysql2/promise');
const fs = require('fs');

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  console.log('=== [1] 读取任务配置 ===');
  const pool = mysql.createPool({ uri: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false }, connectionLimit: 1 });
  const [rows] = await pool.query('SELECT * FROM tasks WHERE id = 1');
  await pool.end();
  const task = rows[0];
  console.log('URL:', task.url);

  console.log('\n=== [2] 启动浏览器 ===');
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
    return {
      name: c.substring(0, idx).trim(),
      value: c.substring(idx + 1).trim(),
      domain: '.' + url.hostname.split('.').slice(-2).join('.'),
      path: '/',
    };
  });
  await ctx.addCookies(cookies);
  console.log(`✅ 注入 ${cookies.length} 个 Cookie`);

  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);

  console.log('\n=== [3] 打开页面 ===');
  await page.goto(task.url, { waitUntil: 'load', timeout: 60000 }).catch(e => console.log('goto:', e.message));
  await sleep(12000);

  // 记录点击前时间
  const text1 = await page.evaluate(() => document.body.innerText).catch(() => '');
  const time1 = text1.match(/(\d{1,2}:\d{2}:\d{2})/);
  console.log('点击前时间:', time1 ? time1[1] : '未找到');

  console.log('\n=== [4] 强制点击 +90 min 按钮 (force: true) ===');
  try {
    const locator = page.locator('button.rt-btn-free').first();
    await locator.click({ force: true, timeout: 5000 });
    console.log('✅ force click 执行完成');
  } catch (e) {
    console.log('force click 异常:', e.message);
  }

  console.log('\n=== [5] 等 8 秒让验证弹窗出现 ===');
  await sleep(8000);

  // 截图
  const ss1 = await page.screenshot({ fullPage: false, type: 'jpeg', quality: 60 });
  fs.writeFileSync('/tmp/captcha-screenshot.jpg', ss1);
  console.log('截图已保存: /tmp/captcha-screenshot.jpg');

  console.log('\n=== [6] 页面所有可见文本 ===');
  const text2 = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log(text2.substring(0, 2000));

  console.log('\n=== [7] 所有 iframe (验证码通常在 iframe 里) ===');
  const frames = page.frames();
  console.log(`iframe 数量: ${frames.length}`);
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i];
    console.log(`\niframe ${i}:`);
    console.log('  URL:', f.url());
    console.log('  name:', f.name());
    try {
      const frameText = await f.evaluate(() => document.body ? document.body.innerText.substring(0, 500) : 'no body').catch(() => 'error');
      console.log('  文本:', frameText);
    } catch {}
  }

  console.log('\n=== [8] 查找验证相关元素 ===');
  const captchaInfo = await page.evaluate(() => {
    const info = {
      // ALTCHA
      altcha: !!document.querySelector('altcha-widget, [data-altcha]'),
      // hCaptcha
      hcaptcha: !!document.querySelector('.h-captcha, iframe[src*="hcaptcha"]'),
      // reCAPTCHA
      recaptcha: !!document.querySelector('.g-recaptcha, iframe[src*="recaptcha"]'),
      // Turnstile
      turnstile: !!document.querySelector('.cf-turnstile, iframe[src*="turnstile"]'),
      // 自定义验证模态框
      modals: [],
      // 所有可见的 button
      visibleButtons: [],
      // 验证相关的关键词
      captchaKeywords: [],
    };

    // 查找所有模态框
    document.querySelectorAll('[id*="modal"], [class*="modal"], [role="dialog"]').forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        info.modals.push({
          tag: el.tagName,
          id: el.id,
          class: (el.className || '').toString().substring(0, 100),
          text: (el.innerText || '').substring(0, 300),
        });
      }
    });

    // 查找所有可见的 button
    document.querySelectorAll('button').forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        const text = (el.innerText || el.textContent || '').trim();
        if (text) {
          info.visibleButtons.push({
            text: text.substring(0, 50),
            class: (el.className || '').toString().substring(0, 80),
            disabled: el.disabled,
          });
        }
      }
    });

    // 查找验证关键词
    const pageText = document.body.innerText.toLowerCase();
    const keywords = ['verify', 'human', 'captcha', 'challenge', 'altcha', 'recaptcha', 'hcaptcha', 'turnstile', '验证', '人机', 'challenge'];
    for (const kw of keywords) {
      if (pageText.includes(kw)) {
        info.captchaKeywords.push(kw);
      }
    }

    return info;
  }).catch(() => null);
  console.log(JSON.stringify(captchaInfo, null, 2));

  console.log('\n=== [9] 验证弹窗的完整 HTML ===');
  const modalHtml = await page.evaluate(() => {
    // 找验证弹窗
    const candidates = [
      document.querySelector('#g4f-ts-modal'),
      document.querySelector('[id*="captcha"]'),
      document.querySelector('[class*="captcha"]'),
      document.querySelector('[id*="verify"]'),
      document.querySelector('[class*="verify"]'),
      document.querySelector('[role="dialog"]'),
    ].filter(Boolean);

    if (candidates.length === 0) return '没找到验证弹窗';
    return candidates.map(el => el.outerHTML).join('\n\n---\n\n').substring(0, 3000);
  }).catch(() => 'error');
  console.log(modalHtml);

  console.log('\n=== [10] 点击后时间 ===');
  const text3 = await page.evaluate(() => document.body.innerText).catch(() => '');
  const time3 = text3.match(/(\d{1,2}:\d{2}:\d{2})/);
  console.log('点击后时间:', time3 ? time3[1] : '未找到');
  if (time1 && time3) {
    const [bh, bm] = time1[1].split(':').map(Number);
    const [ah, am] = time3[1].split(':').map(Number);
    const diff = (ah * 60 + am) - (bh * 60 + bm);
    console.log(`时间变化: ${diff > 0 ? '+' : ''}${diff} 分钟`);
  }

  // 截图
  const ss2 = await page.screenshot({ fullPage: false, type: 'jpeg', quality: 60 });
  fs.writeFileSync('/tmp/captcha-screenshot-after.jpg', ss2);
  console.log('\n最终截图已保存: /tmp/captcha-screenshot-after.jpg');

  await browser.close();
  console.log('\n=== 诊断完成 ===');
})().catch(e => {
  console.error('❌ 异常:', e.message);
  console.error(e.stack);
  process.exit(1);
});
