// 签到任务执行引擎 - zo.computer 版（fetch + Playwright）
// fetch 模式：快速签到，提取剩余时间
// Playwright 模式：过 CF 验证 + 点击按钮（+90 min / Renew）
// 根据 taskType 和是否遇到 CF 自动选择

import { chromium as stealthChromium } from "playwright-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import type { Browser, Page } from "playwright";

stealthChromium.use(StealthPlugin());

// ===== UA 池（5 种） =====
const UA_POOL = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
];

// ===== 视口池（5 种） =====
const VIEWPORT_POOL = [
  { width: 1920, height: 1080 },
  { width: 1536, height: 864 },
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1280, height: 720 },
];

function getRandomFromPool<T>(pool: T[]): T {
  return pool[Math.floor(Math.random() * pool.length)];
}

// 任务级锁，防止同一任务并发执行
// key=task.id, value=启动时间戳
const runningTasks = new Map<number, number>();

export interface CheckinTask {
  id: number;
  name: string;
  url: string;
  username?: string | null;
  password?: string | null;
  renewCycle: number;
  alertDays: number;
  customScript?: string | null;
  taskType?: string | null;
  renewButtonText?: string | null;
  cookies?: string | null;
  renewThresholdMinutes?: number;
  execMode?: number;
  enabled: boolean;
  [key: string]: any;
}

export interface RunResult {
  success: boolean;
  msg: string;
  screenshot?: string;
  remainingTime?: string;
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

function extractSuccessKeyword(customScript: string): string[] | null {
  if (!customScript) return null;
  const match = customScript.match(/SUCCESS_KEYWORD:(.+?)(?:\n|$)/i);
  if (!match) return null;
  const keywords = match[1].split("|").map(k => k.trim()).filter(Boolean);
  return keywords.length > 0 ? keywords : null;
}

/**
 * 解析循环点击配置（从 customScript 字段）
 * 适用场景：gaming4free.net 的 +90min 按钮 - 点击后 4 分钟冷却，可重复点击，上限 48 小时
 * 语法示例：
 *   LOOP_MODE:1
 *   COOLDOWN_SEC:240
 *   CAP_HOURS:48
 *   MAX_CLICKS:35
 */
interface LoopConfig {
  enabled: boolean;
  cooldownSec: number;   // 冷却等待秒数（默认 240 = 4 分钟）
  capHours: number;      // 时间上限（默认 48 小时，达到后停止）
  maxClicks: number;     // 最大点击次数（默认 35，防止无限循环）
}
function extractLoopConfig(customScript: string): LoopConfig {
  const cfg: LoopConfig = {
    enabled: false,
    cooldownSec: 240,
    capHours: 48,
    maxClicks: 35,
  };
  if (!customScript) return cfg;
  const m1 = customScript.match(/LOOP_MODE:\s*(\d+)/i);
  if (m1 && parseInt(m1[1], 10) === 1) cfg.enabled = true;
  const m2 = customScript.match(/COOLDOWN_SEC:\s*(\d+)/i);
  if (m2) cfg.cooldownSec = parseInt(m2[1], 10);
  const m3 = customScript.match(/CAP_HOURS:\s*(\d+)/i);
  if (m3) cfg.capHours = parseInt(m3[1], 10);
  const m4 = customScript.match(/MAX_CLICKS:\s*(\d+)/i);
  if (m4) cfg.maxClicks = parseInt(m4[1], 10);
  return cfg;
}

/**
 * 把页面上的剩余时间字符串解析为分钟数
 * 支持格式：
 *   "05:54:08" → 5*60+54 = 354 分钟
 *   "14:31:55" → 14*60+31 = 871 分钟
 *   "48:00:00" → 48*60 = 2880 分钟
 *   "4天" / "2.5天" → N*1440
 *   "90 min" → 90
 *   "5h 30m" → 330
 */
function parseRemainingMinutes(text: string): number | null {
  if (!text) return null;
  // HH:MM:SS
  let m = text.match(/(\d{1,3}):(\d{2}):(\d{2})/);
  if (m) {
    return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
  }
  // MM:SS （冷却时间格式，如 "03:06"）
  m = text.match(/(^|\D)(\d{1,2}):(\d{2})(?:\.(\d+))?($|\D)/);
  if (m) {
    return parseInt(m[2], 10);
  }
  // N天 / N days
  m = text.match(/(\d+(?:\.\d+)?)\s*(?:天|days?)/i);
  if (m) {
    return Math.round(parseFloat(m[1]) * 1440);
  }
  // N小时 / N hours / Nh
  m = text.match(/(\d+(?:\.\d+)?)\s*(?:小时|hours?|h)\b/i);
  if (m) {
    return Math.round(parseFloat(m[1]) * 60);
  }
  // N min / N分钟
  m = text.match(/(\d+)\s*(?:分钟|mins?|minutes?)\b/i);
  if (m) {
    return parseInt(m[1], 10);
  }
  return null;
}

/**
 * 检测按钮当前是否可点击（未被冷却禁用）
 * 返回: 'clickable' | 'cooldown' | 'missing' | 'capped'
 *
 * 重要：gaming4free 点完 +90min 后，按钮会从 DOM 消失，被冷却倒计时（如 03:06.68）替换。
 * 所以找不到按钮文字 ≠ 任务结束，需要再检查页面上是否有冷却/上限指示器。
 * 按钮文字匹配时忽略空格，这样 "+90 min" 能匹配到页面上的 "+ 90 min"
 */
async function checkButtonState(page: any, buttonText: string): Promise<'clickable' | 'cooldown' | 'missing' | 'capped'> {
  try {
    const state = await page.evaluate((target: string) => {
      const normalizedTarget = target.toLowerCase().replace(/\s+/g, "");
      // 1. 先按文字找按钮（忽略空格匹配）
      const clickables = document.querySelectorAll("button, a, [role='button'], [onclick], .btn, .button");
      for (const el of clickables) {
        const text = ((el as any).innerText || el.textContent || "").toLowerCase().replace(/\s+/g, "");
        if (text && text.includes(normalizedTarget)) {
          const btn = el as HTMLButtonElement;
          if (btn.disabled) return { found: true, disabled: true, reason: "disabled" };
          if (btn.getAttribute("aria-disabled") === "true") return { found: true, disabled: true, reason: "aria" };
          const cls = (btn.className || "").toString().toLowerCase();
          if (cls.includes("disabled")) return { found: true, disabled: true, reason: "class" };
          const style = window.getComputedStyle(btn);
          if (style.pointerEvents === "none" || style.opacity === "0") {
            return { found: true, disabled: true, reason: "style" };
          }
          return { found: true, disabled: false, reason: "ok" };
        }
      }
      // 2. 按钮没找到，检查页面是否在冷却中
      const pageText = (document.body.innerText || "").toLowerCase();
      // 冷却指示器：MM:SS 倒计时、cooldown/cd 字样
      const hasCooldownTimer = /\b\d{1,2}:\d{2}(\.\d+)?\b/.test(pageText);
      const hasCooldownKeyword = /cooldown|cool-down|冷却|cd\b|countdown|count-down|waiting/i.test(pageText);
      // 上限指示器：cap 48h / limit / 上限
      const hasCap = /cap\s*\d|h\s*cap|limit\s*\d|上限|max\s*time/i.test(pageText);
      // 是否还有 "remaining" / "expires" 倒计时（说明任务在跑）
      const hasRemaining = /remain|expires|剩余|到期/i.test(pageText);
      return {
        found: false,
        disabled: false,
        hasCooldown: hasCooldownTimer || hasCooldownKeyword,
        hasCap,
        hasRemaining,
      };
    }, buttonText);

    if (state.found) {
      return state.disabled ? 'cooldown' : 'clickable';
    }
    // 按钮没找到
    if (state.hasCap && !state.hasRemaining) return 'capped';
    if (state.hasCooldown || state.hasRemaining) return 'cooldown'; // 冷却中（按钮被替换成倒计时）
    return 'missing';
  } catch {
    return 'missing';
  }
}

/**
 * 单次点击按钮（不抛异常）
 * 重要: 按钮文字匹配时会忽略空格，这样 "+90 min" 能匹配到页面上的 "+ 90 min"
 * 改进: 用 Playwright 真实鼠标点击（hover + click），而不是 DOM .click()
 *       因为 gaming4free 的按钮可能需要真实的鼠标事件才能触发
 */
async function clickButtonOnce(page: any, buttonText: string): Promise<boolean> {
  // 先尝试原始文字（精确匹配）
  const variants = [buttonText, buttonText.replace(/\s+/g, ""), buttonText.replace(/\s+/g, " ").trim()];
  
  // 方法 1: getByRole - 用 Playwright 真实鼠标点击（hover 后 click）
  for (const v of variants) {
    try {
      const locator = page.getByRole("button", { name: v, exact: false });
      if (await locator.count() > 0) {
        const btn = locator.first();
        // 先 hover 模拟真实鼠标移动
        await btn.hover({ timeout: 3000 }).catch(() => {});
        await sleep(500);
        // 用真实鼠标点击（force: true 强制点击，忽略遮挡）
        await btn.click({ timeout: 5000, force: false });
        return true;
      }
    } catch {}
  }
  
  // 方法 2: text= 选择器 + 真实鼠标点击
  for (const v of variants) {
    try {
      const locator = page.locator(`text="${v}"`).first();
      if (await locator.isVisible().catch(() => false)) {
        await locator.hover({ timeout: 3000 }).catch(() => {});
        await sleep(500);
        await locator.click({ timeout: 5000 });
        return true;
      }
    } catch {}
  }
  
  // 方法 2.5: 用 CSS class 找按钮 (仅 gaming4free 域名, 避免 katabump 误匹配)
  const currentHost = new URL(page.url()).hostname;
  if (currentHost.includes('gaming4free')) {
    const classPatterns = ["rt-btn-free", "btn-renew", "btn-free", "renew-btn"];
    for (const cls of classPatterns) {
      try {
        const locator = page.locator(`button.${cls}, .${cls}`).first();
        if (await locator.isVisible().catch(() => false)) {
          await locator.hover({ timeout: 3000 }).catch(() => {});
          await sleep(500);
          // 用真实鼠标点击（模拟人类操作，过 Turnstile）
          const btnBox = await locator.boundingBox().catch(() => null);
          if (btnBox) {
            // 随机起点移动
            const startX = btnBox.x + btnBox.width / 2 + (Math.random() - 0.5) * 80;
            const startY = btnBox.y + btnBox.height / 2 + (Math.random() - 0.5) * 80;
            await page.mouse.move(startX, startY, { steps: 12 });
            await sleep(300 + Math.random() * 600);
            // 移动到按钮中心
            const targetX = btnBox.x + btnBox.width / 2;
            const targetY = btnBox.y + btnBox.height / 2;
            await page.mouse.move(targetX, targetY, { steps: 18 });
            await sleep(200 + Math.random() * 400);
            // 真实点击
            await page.mouse.click(targetX, targetY);
            console.log(`[taskService] ✅ 用真实鼠标点击 "${cls}"，等 Turnstile`);
          } else {
            await locator.click({ timeout: 10000 });
            console.log(`[taskService] ✅ fallback 点击 "${cls}"，等 Turnstile`);
          }
          
          // 等 Turnstile 模态框出现（gaming4free 特有）
          try {
            await page.waitForFunction(() => {
              const modal = document.getElementById('g4f-ts-modal');
              return modal && modal.style.display !== 'none';
            }, { timeout: 5000 });
            console.log(`[taskService] ✅ Turnstile 模态框已出现`);
            
            // 等 Turnstile 自动通过（stealth 插件）
            await sleep(8000);
            
            // 等模态框关闭（验证通过）
            await page.waitForFunction(() => {
              const modal = document.getElementById('g4f-ts-modal');
              return !modal || modal.style.display === 'none';
            }, { timeout: 20000 });
            console.log(`[taskService] ✅ Turnstile 验证通过`);
          } catch (e: any) {
            console.log(`[taskService] ⚠️ Turnstile 模态框未出现或未关闭: ${(e as Error).message}`);
          }
          return true;
        }
      } catch {}
    }
  }
  
  // 方法 3: evaluate 找到按钮坐标, 然后用 Playwright 鼠标点击坐标
  try {
    const box = await page.evaluate((target: string) => {
      const normalizedTarget = target.toLowerCase().replace(/\s+/g, "");
      const clickables = document.querySelectorAll("button, a, [role='button'], [onclick]");
      for (const el of clickables) {
        const text = ((el as any).innerText || el.textContent || "").toLowerCase().replace(/\s+/g, "");
        if (text && text.includes(normalizedTarget)) {
          const btn = el as HTMLButtonElement;
          if (btn.disabled) continue;
          const rect = btn.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, text };
          }
        }
      }
      return null;
    }, buttonText);
    
    if (box) {
      // 用 Playwright 鼠标 API 真实点击坐标
      await page.mouse.move(box.x, box.y);
      await sleep(300);
      await page.mouse.click(box.x, box.y);
      console.log(`[taskService] ✅ 通过鼠标坐标点击成功 (${box.x}, ${box.y})`);
      return true;
    }
  } catch {}
  
  // 方法 4: 最后兜底用 DOM .click() (可能不触发事件, 但聊胜于无)
  try {
    const result = await page.evaluate((target: string) => {
      const normalizedTarget = target.toLowerCase().replace(/\s+/g, "");
      const clickables = document.querySelectorAll("button, a, [role='button'], [onclick]");
      for (const el of clickables) {
        const text = ((el as any).innerText || el.textContent || "").toLowerCase().replace(/\s+/g, "");
        if (text && text.includes(normalizedTarget)) {
          const btn = el as HTMLButtonElement;
          if (btn.disabled) continue;
          // 触发完整的鼠标事件序列
          const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
          for (const evt of events) {
            el.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
          }
          return text;
        }
      }
      return null;
    }, buttonText);
    if (result) {
      console.log(`[taskService] ✅ 通过事件序列点击成功`);
      return true;
    }
  } catch {}
  return false;
}

/**
 * 处理 Cloudflare Turnstile 验证
 * gaming4free 点击 +90 min 后会弹出 Turnstile 验证窗口 (#g4f-ts-modal)
 * 在 stealth 模式下 Turnstile 通常会自动通过，需要等待 + 触发
 *
 * 返回: true=验证通过 / false=验证失败或超时
 */
async function handleTurnstileCaptcha(page: any, maxWaitMs: number = 60000): Promise<boolean> {
  console.log("[taskService] 🔍 检测 Turnstile 验证弹窗...");
  
  // 1. 等 Turnstile 弹窗出现（点击后需要 1-3 秒才会弹出）
  console.log("[taskService] ⏳ 等待 Turnstile 弹窗出现...");
  let modalVisible = false;
  try {
    await page.waitForFunction(() => {
      const modal = document.getElementById('g4f-ts-modal');
      if (!modal) return false;
      const style = window.getComputedStyle(modal);
      return style.display !== 'none' && style.display !== '';
    }, { timeout: 15000 });  // 增加到 15 秒，避免误判
    modalVisible = true;
    console.log("[taskService] ✅ Turnstile 弹窗已出现");
  } catch {
    console.log("[taskService] ⚠️ 15 秒内未出现 Turnstile 弹窗，可能不需要验证");
    return true;
  }
  
  // 模拟人类行为：在验证弹窗出现后，随机移动鼠标 3-5 秒
  console.log("[taskService] 🖱️ 模拟人类鼠标移动...");
  for (let i = 0; i < 5; i++) {
    const x = 200 + Math.random() * 1520;
    const y = 200 + Math.random() * 680;
    await page.mouse.move(x, y, { steps: 10 + Math.floor(Math.random() * 15) });
    await sleep(500 + Math.random() * 1000);
  }
  console.log("[taskService] ⏳ Turnstile 验证弹窗已出现，等待自动通过...");
  
  // 记录点击前的剩余时间，用于判断是否真的续期成功
  let beforeTime: string | null = null;
  try {
    const beforeText = await page.evaluate(() => document.body.innerText).catch(() => "");
    beforeTime = extractRemainingTime(beforeText);
    console.log(`[taskService] ⏰ 验证前剩余时间: ${beforeTime || "未提取到"}`);
  } catch {}
  
  // 2. 等待 Turnstile widget 渲染并自动验证
  const startTime = Date.now();
  let hasFailureRetry = false;  // 检测是否有 failure_retry
  
  while (Date.now() - startTime < maxWaitMs) {
    await sleep(2000);
    
    // 检查 Turnstile iframe URL 是否包含 failure_retry（表示验证失败）
    try {
      const frames = page.frames();
      for (const frame of frames) {
        const url = frame.url();
        if (url.includes('challenges.cloudflare.com') || url.includes('turnstile')) {
          if (url.includes('failure_retry')) {
            hasFailureRetry = true;
            console.log(`[taskService] ⚠️ 检测到 failure_retry，Turnstile 验证失败`);
          } else if (hasFailureRetry) {
            // 之前有 failure_retry，现在没有了，说明重新验证了
            hasFailureRetry = false;
            console.log(`[taskService] ✅ failure_retry 消失，重新验证中`);
          }
          break;
        }
      }
    } catch {}
    
    // 检查弹窗是否消失（验证通过后弹窗会关闭）
    try {
      const display = await page.evaluate(() => {
        const modal = document.getElementById('g4f-ts-modal');
        if (!modal) return 'gone';
        return window.getComputedStyle(modal).display;
      }).catch(() => 'error');
      
      if (display === 'none' || display === 'gone') {
        // 弹窗关闭了，检查剩余时间是否增加来判断是否真的通过
        const afterText = await page.evaluate(() => document.body.innerText).catch(() => "");
        const afterTime = extractRemainingTime(afterText);
        console.log(`[taskService] ⏰ 验证后剩余时间: ${afterTime || "未提取到"}`);
        
        // 对比时间是否增加
        if (beforeTime && afterTime) {
          const beforeMins = parseRemainingMinutes(beforeTime);
          const afterMins = parseRemainingMinutes(afterTime);
          if (beforeMins !== null && afterMins !== null && afterMins > beforeMins) {
            console.log(`[taskService] ✅ Turnstile 弹窗已关闭，剩余时间增加 ${afterMins - beforeMins} 分钟，验证通过！`);
            return true;
          } else {
            console.log(`[taskService] ⚠️ Turnstile 弹窗已关闭，但剩余时间未增加 (${beforeTime} → ${afterTime})，验证可能失败`);
            return false;  // 时间没增加，说明验证失败
          }
        }
        
        // 如果无法提取时间，检查是否有 failure_retry
        if (hasFailureRetry) {
          console.log("[taskService] ⚠️ Turnstile 弹窗已关闭，但有 failure_retry，验证失败");
          return false;
        }
        
        console.log("[taskService] ✅ Turnstile 弹窗已关闭，无法提取时间，假定验证通过");
        return true;
      }
    } catch {}
    
    // 3. 尝试点击 Turnstile checkbox（如果有）
    try {
      const frames = page.frames();
      for (const frame of frames) {
        const url = frame.url();
        if (url.includes('challenges.cloudflare.com') || url.includes('turnstile')) {
          console.log(`[taskService] 找到 Turnstile iframe: ${url.substring(0, 100)}...`);
          // 尝试用真实鼠标点击 checkbox（模拟人类操作）
          try {
            const checkbox = frame.locator('input[type="checkbox"], .cb-i, .mark').first();
            if (await checkbox.isVisible({ timeout: 2000 }).catch(() => false)) {
              // 获取 checkbox 的坐标
              const box = await checkbox.boundingBox().catch(() => null);
              if (box) {
                console.log(`[taskService] 📍 checkbox 坐标: x=${box.x}, y=${box.y}, w=${box.width}, h=${box.height}`);
                // 先随机移动鼠标（模拟人类移动轨迹）
                const startX = box.x + box.width / 2 + (Math.random() - 0.5) * 100;
                const startY = box.y + box.height / 2 + (Math.random() - 0.5) * 100;
                await page.mouse.move(startX, startY, { steps: 15 });
                await sleep(300 + Math.random() * 700);
                // 移动到 checkbox 中心
                const targetX = box.x + box.width / 2;
                const targetY = box.y + box.height / 2;
                await page.mouse.move(targetX, targetY, { steps: 20 });
                await sleep(200 + Math.random() * 500);
                // 真实点击
                await page.mouse.click(targetX, targetY);
                console.log("[taskService] ✅ 用真实鼠标点击了 Turnstile checkbox");
                await sleep(2000);
              } else {
                // fallback: 直接点击
                await checkbox.click({ timeout: 2000 }).catch(() => {});
                console.log("[taskService] ✅ fallback 点击了 Turnstile checkbox");
              }
            }
          } catch (e: any) {
            console.log(`[taskService] ⚠️ 点击 checkbox 失败: ${(e as Error).message}`);
          }
          break;
        }
      }
    } catch {}
    
    // 4. 检查按钮是否还在 loading 状态
    try {
      const btnText = await page.evaluate(() => {
        const btn = document.querySelector('button.rt-btn-free');
        if (!btn) return 'not-found';
        return ((btn as HTMLElement).innerText || btn.textContent || '').trim();
      }).catch(() => 'error');
      console.log(`[taskService] 按钮当前文字: ${btnText}`);
      
      // 如果按钮恢复成 "+ 90 min" 且 enabled，检查时间是否增加
      if (btnText && (btnText.includes('+') || btnText.includes('90')) && !btnText.includes('loading')) {
        // 检查剩余时间是否增加
        const afterText = await page.evaluate(() => document.body.innerText).catch(() => "");
        const afterTime = extractRemainingTime(afterText);
        if (beforeTime && afterTime) {
          const beforeMins = parseRemainingMinutes(beforeTime);
          const afterMins = parseRemainingMinutes(afterTime);
          if (beforeMins !== null && afterMins !== null && afterMins > beforeMins) {
            console.log(`[taskService] ✅ 按钮恢复可点击状态，剩余时间增加 ${afterMins - beforeMins} 分钟，验证通过！`);
            return true;
          } else {
            console.log(`[taskService] ⚠️ 按钮恢复可点击状态，但剩余时间未增加 (${beforeTime} → ${afterTime})，验证失败`);
            return false;
          }
        }
        // 无法提取时间，检查 failure_retry
        if (hasFailureRetry) {
          console.log("[taskService] ⚠️ 按钮恢复，但有 failure_retry，验证失败");
          return false;
        }
        console.log("[taskService] ✅ 按钮恢复可点击状态，无法提取时间，假定验证通过");
        return true;
      }
    } catch {}
  }
  
  console.log(`[taskService] ⏰ Turnstile 验证超时 (${maxWaitMs}ms)`);
  return false;
}

function extractRemainingTime(html: string): string | null {
  const text = html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  // gaming4free 格式: "02:28:07remaining" (时间紧贴 remaining 关键字)
  let m = text.match(/(\d{1,2}:\d{2}:\d{2})\s*remain/i);
  if (m) return m[1];
  m = text.match(/remain\w*\s*(\d{1,2}:\d{2}:\d{2})/i);
  if (m) return m[1];
  m = text.match(/Expires\s*in[:\s]*(\d{1,2}:\d{2}:\d{2})/i);
  if (m) return m[1];
  m = text.match(/(\d{1,2}:\d{2}:\d{2})\s*(?:remain|remaining)/i);
  if (m) return m[1];
  m = text.match(/remain\w*\s*(\d{1,2}:\d{2}:\d{2})/i);
  if (m) return m[1];
  m = text.match(/(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:cd|cooldown)/i);
  if (m) return m[1] + " (冷却中)";
  m = text.match(/还有\s*(\d+)\s*天/);
  if (m) return m[1] + " 天";
  // host2play 格式: "Deletes on 2026/07/12 12:00" (确保有日期才返回)
  m = text.match(/Deletes?\s*on[:\s]+(\d{4}\/\d{1,2}\/\d{1,2}\s+\d{1,2}:\d{2})/i);
  if (m) return "到期: " + m[1].trim();
  // host2play 格式: "Expires on 2026/07/12" 
  m = text.match(/Expires?\s*on[:\s]+(\d{4}\/\d{1,2}\/\d{1,2})/i);
  if (m) return "到期: " + m[1].trim();
  // gaming4free 格式: "expires 19:23" (到期时间)
  m = text.match(/expires\s*(\d{1,2}:\d{2})/i);
  if (m) return m[1];
  // 通用: "到期: XXX" 确保有内容才返回
  m = text.match(/到期[:\s]+(\S+)/i);
  if (m && m[1] && m[1].length > 2) return "到期: " + m[1];
  return null;
}

function parseCookies(cookieStr: string, url: string): any[] {
  if (!cookieStr || !cookieStr.trim()) return [];
  const urlObj = new URL(url);
  const domain = urlObj.hostname;
  const isHttps = urlObj.protocol === "https:";
  if (cookieStr.trim().startsWith("[")) {
    try { return JSON.parse(cookieStr); } catch {}
  }
  const cookies: any[] = [];
  const parts = cookieStr.split(/\s*;\s*/);
  for (const part of parts) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    const name = part.substring(0, idx).trim();
    const value = part.substring(idx + 1).trim();
    if (!name) continue;
    cookies.push({ name, value, domain, path: "/", httpOnly: false, secure: isHttps, sameSite: "Lax" as const });
  }
  return cookies;
}

/**
 * 主入口
 */
export async function manualRunTask(task: CheckinTask): Promise<RunResult> {
  console.log(`[taskService] 开始执行任务: ${task.name} (id=${task.id})`);
  console.log(`[taskService] URL: ${task.url}`);
  console.log(`[taskService] 任务类型: ${task.taskType || "link"}`);

  // 任务级锁：防止同一任务并发执行（循环点击任务会跑很久，期间不能重复触发）
  if (runningTasks.has(task.id)) {
    const startedAt = runningTasks.get(task.id)!;
    const elapsedMin = Math.floor((Date.now() - startedAt) / 60000);
    const msg = `⚠️ 任务正在执行中（已运行 ${elapsedMin} 分钟），跳过本次触发`;
    console.log(`[taskService] ${msg}`);
    return { success: false, msg };
  }

  runningTasks.set(task.id, Date.now());
  try {
    const taskType = task.taskType || "link";

    // link 类型先用 fetch（快速，省资源）
    if (taskType === "link") {
      const fetchResult = await runFetchTask(task);
      
      // 如果 fetch 成功且没有遇到 CF，直接返回
      if (fetchResult.success && !fetchResult.msg.includes("CF 验证")) {
        return fetchResult;
      }

      // 如果遇到 CF 验证，且有 Cookie，尝试用 Playwright
      if (!fetchResult.success && fetchResult.msg.includes("CF 验证") && task.cookies) {
        console.log("[taskService] fetch 遇到 CF，切换到 Playwright 模式");
        const browserResult = await runPlaywrightTask(task);
        return browserResult;
      }

      return fetchResult;
    }

    // 其他类型用 Playwright
    return await runPlaywrightTask(task);
  } finally {
    runningTasks.delete(task.id);
  }
}

/**
 * fetch 签到模式
 */
async function runFetchTask(task: CheckinTask): Promise<RunResult> {
  console.log("[taskService] fetch 签到模式");
  const startTime = Date.now();

  try {
    const headers: Record<string, string> = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    };

    if (task.cookies && task.cookies.trim()) {
      let cookieStr = task.cookies.trim();
      if (cookieStr.startsWith("[")) {
        try {
          const arr = JSON.parse(cookieStr);
          cookieStr = arr.map((c: any) => `${c.name}=${c.value}`).join("; ");
        } catch {}
      }
      headers["Cookie"] = cookieStr;
      console.log(`[taskService] 携带 Cookie (${cookieStr.length} 字符)`);
    }

    const { default: https } = await import("https");
    const { default: http } = await import("http");
    const urlObj = new URL(task.url);
    const isHttps = urlObj.protocol === "https:";

    const respData: { status: number; text: string } = await new Promise((resolve, reject) => {
      const req = (isHttps ? https : http).request({
        hostname: urlObj.hostname,
        port: urlObj.port || (isHttps ? 443 : 80),
        path: urlObj.pathname + urlObj.search,
        method: "GET",
        headers,
        timeout: 30000,
      }, (resp) => {
        let data = "";
        resp.on("data", chunk => data += chunk);
        resp.on("end", () => resolve({ status: resp.statusCode || 0, text: data }));
      });
      req.on("error", reject);
      req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
      req.end();
    });

    const duration = Date.now() - startTime;
    const status = respData.status;
    const text = respData.text;
    console.log(`[taskService] 响应状态: ${status}, 耗时: ${duration}ms, 内容长度: ${text.length}`);

    const remainingTime = extractRemainingTime(text);
    if (remainingTime) console.log(`[taskService] ⏰ 剩余时间: ${remainingTime}`);

    // 检测 CF
    const isCF = (status === 403 || status === 503) &&
      (text.includes("Just a moment") || text.includes("challenge-platform") || text.includes("请验证你是真人"));
    if (isCF) {
      return { success: false, msg: `⚠️ CF 验证未通过，需要手动续期\n链接: ${task.url}`, remainingTime: remainingTime || undefined };
    }

    if (status >= 200 && status < 400) {
      // 特殊处理：302 重定向 + URL 包含 renew=success，说明续期成功（KataBump 等站点）
      if (status === 302 && task.url.includes("renew=success")) {
        console.log("[taskService] ✅ 302 重定向 + renew=success URL, 判定为续期成功");
        return { success: true, msg: `续期成功 (HTTP 302 重定向, ${duration}ms)`, remainingTime: remainingTime || undefined };
      }
      
      const errorKeywords = ["error", "failed", "invalid", "expired token", "登录失败", "续期失败", "unauthorized", "请先登录"];
      const lowerText = text.toLowerCase();
      const foundError = errorKeywords.find(kw => lowerText.includes(kw.toLowerCase()));
      const successKeyword = extractSuccessKeyword(task.customScript || "");

      if (foundError && !lowerText.includes("success")) {
        return { success: false, msg: `HTTP ${status} 错误关键词 "${foundError}"`, remainingTime: remainingTime || undefined };
      }
      if (successKeyword) {
        const matched = successKeyword.find(kw => text.includes(kw));
        if (matched) return { success: true, msg: `签到成功 (HTTP ${status}, 关键词 "${matched}", ${duration}ms)`, remainingTime: remainingTime || undefined };
        // 302 + 空 content 也算成功（重定向通常 content 为空）
        if (status === 302) {
          return { success: true, msg: `续期成功 (HTTP 302 重定向, ${duration}ms)`, remainingTime: remainingTime || undefined };
        }
        return { success: false, msg: `HTTP ${status} 未包含成功关键词 [${successKeyword.join("|")}]`, remainingTime: remainingTime || undefined };
      }
      return { success: true, msg: `签到成功 (HTTP ${status}, ${duration}ms)`, remainingTime: remainingTime || undefined };
    }
    return { success: false, msg: `HTTP ${status}`, remainingTime: remainingTime || undefined };
  } catch (e: any) {
    return { success: false, msg: `签到异常: ${e.message}` };
  }
}

/**
 * 自动填表登录（多选择器覆盖）
 * 13+ 种用户名选择器 + 7+ 种密码选择器 + 14+ 种登录按钮选择器
 */
async function autoFillLoginForm(page: any, username: string, password: string): Promise<boolean> {
  // 用户名选择器（13+ 种）
  const usernameSelectors = [
    'input[name="username"]', 'input[name="user"]', 'input[name="account"]',
    'input[name="email"]', 'input[name="login"]', 'input[name="userid"]',
    'input[type="email"]', 'input[type="text"][name*="user"]',
    'input[type="text"][name*="account"]', 'input[type="text"][name*="email"]',
    '#username', '#user', '#email', '#account',
    'input[placeholder*="用户名"]', 'input[placeholder*="账号"]', 'input[placeholder*="邮箱"]',
  ];

  // 密码选择器（7+ 种）
  const passwordSelectors = [
    'input[name="password"]', 'input[name="passwd"]', 'input[name="pwd"]',
    'input[type="password"]', '#password', '#passwd', '#pwd',
    'input[placeholder*="密码"]',
  ];

  // 登录按钮选择器（14+ 种）
  const loginButtonSelectors = [
    'button[type="submit"]', 'button[type="button"][name*="login"]',
    'button[name*="login"]', 'button[class*="login"]', 'button[id*="login"]',
    'input[type="submit"]', 'input[type="button"][value*="登录"]', 'input[type="button"][value*="Login"]',
    'a[class*="login"]', 'a[id*="login"]',
    'button:has-text("登录")', 'button:has-text("Login")', 'button:has-text("Sign in")',
    '[role="button"]:has-text("登录")',
  ];

  console.log("[autoFill] 开始查找用户名输入框...");
  let usernameFilled = false;
  for (const selector of usernameSelectors) {
    try {
      const el = page.locator(selector).first();
      if (await el.isVisible({ timeout: 1000 }).catch(() => false)) {
        await el.fill(username);
        console.log(`[autoFill] ✅ 用户名填入成功: ${selector}`);
        usernameFilled = true;
        break;
      }
    } catch {}
  }

  if (!usernameFilled) {
    console.log("[autoFill] ❌ 未找到用户名输入框");
    return false;
  }

  console.log("[autoFill] 开始查找密码输入框...");
  let passwordFilled = false;
  for (const selector of passwordSelectors) {
    try {
      const el = page.locator(selector).first();
      if (await el.isVisible({ timeout: 1000 }).catch(() => false)) {
        await el.fill(password);
        console.log(`[autoFill] ✅ 密码填入成功: ${selector}`);
        passwordFilled = true;
        break;
      }
    } catch {}
  }

  if (!passwordFilled) {
    console.log("[autoFill] ❌ 未找到密码输入框");
    return false;
  }

  console.log("[autoFill] 开始查找登录按钮...");
  let loginClicked = false;
  for (const selector of loginButtonSelectors) {
    try {
      const el = page.locator(selector).first();
      if (await el.isVisible({ timeout: 1000 }).catch(() => false)) {
        await el.click();
        console.log(`[autoFill] ✅ 点击登录按钮成功: ${selector}`);
        loginClicked = true;
        break;
      }
    } catch {}
  }

  if (!loginClicked) {
    // 兜底：按 Enter 键提交
    await page.keyboard.press("Enter");
    console.log("[autoFill] ⚠️ 未找到登录按钮，按 Enter 提交");
    loginClicked = true;
  }

  // 等待页面跳转
  await sleep(3000);
  console.log("[autoFill] ✅ 登录流程完成");
  return true;
}

/**
 * Playwright 签到模式（过 CF + 点击按钮）
 */
async function runPlaywrightTask(task: CheckinTask): Promise<RunResult> {
  console.log("[taskService] Playwright 签到模式");
  let browser: any = null;
  let screenshot: string | undefined;

  try {
    // 终极反检测启动参数
    const launchArgs = [
      "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
      "--disable-gpu", "--disable-infobars", "--window-size=1920,1080",
      "--disable-blink-features=AutomationControlled",
      // 新增：隐藏自动化痕迹
      "--disable-features=IsolateOrigins,site-per-process",
      "--disable-site-isolation-trials",
      "--no-first-run", "--no-default-browser-check",
      "--password-store=basic", "--use-mock-keychain",
      // 新增：模拟真实 GPU
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
      // 新增：禁用 DevTools 协议检测
      "--disable-dev-shm-usage",
      "--remote-debugging-port=0",
    ];

    browser = await stealthChromium.launch({
      headless: process.env.DISPLAY ? false : true,
      args: launchArgs,
      // 新增：忽略默认参数，避免被检测
      ignoreDefaultArgs: ["--enable-automation"],
    });

    // 随机选择 UA 和视口
    const randomUA = getRandomFromPool(UA_POOL);
    const randomViewport = getRandomFromPool(VIEWPORT_POOL);
    console.log(`[taskService] 🕵️ 使用 UA: ${randomUA.substring(0, 50)}...`);
    console.log(`[taskService] 🕵️ 使用视口: ${randomViewport.width}x${randomViewport.height}`);
    console.log(`[taskService] 🕵️ 使用 headless: ${process.env.DISPLAY ? false : true}`);

    const context = await browser.newContext({
      userAgent: randomUA,
      viewport: randomViewport,
      locale: "zh-CN",
      timezoneId: "Asia/Shanghai",
      // 新增：地理定位（模拟真实用户）
      geolocation: { latitude: 31.2304, longitude: 121.4737 },
      permissions: ["geolocation"],
      extraHTTPHeaders: {
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    });

    // 终极反检测脚本（15 项指纹伪造）
    await context.addInitScript(() => {
      // 1. 隐藏 webdriver（多种方式）
      Object.defineProperty(navigator, "webdriver", { get: () => undefined });
      delete (navigator as any).__proto__.webdriver;
      
      // 2. 伪造 plugins（更真实）
      Object.defineProperty(navigator, "plugins", {
        get: () => {
          const plugins = [
            { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer", description: "Portable Document Format" },
            { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", description: "" },
            { name: "Native Client", filename: "internal-nacl-plugin", description: "" },
          ];
          return plugins;
        },
      });
      
      // 3. 伪造 languages
      Object.defineProperty(navigator, "languages", { get: () => ["zh-CN", "zh", "en-US", "en"] });
      
      // 4. 伪造 platform
      Object.defineProperty(navigator, "platform", { get: () => "Win32" });
      
      // 5. 伪造 hardwareConcurrency
      Object.defineProperty(navigator, "hardwareConcurrency", { get: () => 8 });
      
      // 6. 伪造 deviceMemory
      Object.defineProperty(navigator, "deviceMemory", { get: () => 8 });
      
      // 7. 伪造 WebGL 指纹（更完整）
      const getParameter = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(parameter: number) {
        if (parameter === 37445) return "Intel Inc.";
        if (parameter === 37446) return "Intel Iris OpenGL Engine";
        if (parameter === 7937) return "Intel Iris OpenGL Engine";
        return getParameter.call(this, parameter);
      };
      
      // 8. 伪造 Chrome 对象（更完整）
      (window as any).chrome = {
        runtime: {
          OnInstalledReason: { CHROME_UPDATE: "chrome_update", INSTALL: "install", UPDATE: "update" },
          OnRestartRequiredReason: { APP_UPDATE: "app_update", OS_UPDATE: "os_update", PERIODIC: "periodic" },
          PlatformArch: { ARM: "arm", X86_32: "x86-32", X86_64: "x86-64" },
          connect: () => {}, sendMessage: () => {},
        },
        loadTimes: () => ({ requestTime: Date.now() / 1000, startLoadTime: Date.now() / 1000, commitLoadTime: Date.now() / 1000, finishDocumentLoadTime: Date.now() / 1000, finishLoadTime: Date.now() / 1000, firstPaintTime: Date.now() / 1000, firstPaintAfterLoadTime: Date.now() / 1000, navigationType: "Other", wasFetchedViaSpdy: true, wasNpnNegotiated: true, npnNegotiatedProtocol: "h2", wasAlternateProtocolAvailable: false, connectionInfo: "h2" }),
        csi: () => ({ startE: Date.now(), onloadT: Date.now(), pageT: Date.now() - Date.now(), tran: 15 }),
        app: { isInstalled: false, InstallState: { DISABLED: "disabled", INSTALLED: "installed", NOT_INSTALLED: "not_installed" }, RunningState: { CANNOT_RUN: "cannot_run", READY_TO_RUN: "ready_to_run", RUNNING: "running" } },
      };
      
      // 9. 伪造 permissions API
      const originalQuery = (window as any).navigator.permissions.query;
      (window as any).navigator.permissions.query = (parameters: any) => (
        parameters.name === "notifications" ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters)
      );
      
      // 10. 伪造 canvas 指纹（添加噪声）
      const toDataURL = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = function(...args: any[]) {
        const ctx = this.getContext("2d");
        if (ctx) {
          const imageData = ctx.getImageData(0, 0, this.width, this.height);
          for (let i = 0; i < imageData.data.length; i += 4) {
            imageData.data[i] += Math.floor(Math.random() * 10) - 5;
            imageData.data[i + 1] += Math.floor(Math.random() * 10) - 5;
            imageData.data[i + 2] += Math.floor(Math.random() * 10) - 5;
          }
          ctx.putImageData(imageData, 0, 0);
        }
        return toDataURL.apply(this, args as any);
      };
      
      // 11. 伪造 AudioContext 指纹
      const getChannelData = AudioBuffer.prototype.getChannelData;
      AudioBuffer.prototype.getChannelData = function(channel: number) {
        const data = getChannelData.call(this, channel);
        for (let i = 0; i < data.length; i += 100) { data[i] += Math.random() * 0.0001; }
        return data;
      };
      
      // 12. 新增：隐藏 CDP 检测
      (window as any).navigator.connection = { rt: 50, downlink: 10, effectiveType: "4g", saveData: false };
      
      // 13. 新增：伪造 battery API
      (navigator as any).getBattery = () => Promise.resolve({
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1,
        addEventListener: () => {}, removeEventListener: () => {},
      });
      
      // 14. 新增：隐藏 Playwright 痕迹
      const originalDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
      Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
        get: function() { return originalDescriptor?.get?.call(this) || 0; },
      });
      
      // 15. 新增：伪造 toString 检测
      const originalToString = Function.prototype.toString;
      Function.prototype.toString = function() {
        if (this === Function.prototype.toString) return "function toString() { [native code] }";
        return originalToString.call(this);
      };
    });

    // Cookie 注入
    if (task.cookies && task.cookies.trim()) {
      const cookies = parseCookies(task.cookies, task.url);
      if (cookies.length > 0) {
        await context.addCookies(cookies);
        console.log(`[taskService] ✅ 注入 ${cookies.length} 个 Cookie`);
      }
    }

    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    page.setDefaultNavigationTimeout(60000);

    // 自动填表（login 类型）
    if (task.taskType === "login" && task.username && task.password) {
      console.log("[taskService] 🔐 自动填表模式");
      await autoFillLoginForm(page, task.username, task.password);
    }

    // 打开 URL
    console.log("[taskService] 打开 URL");
    
    // 检测是否是 KataBump（有 Cloudflare 保护，需要特殊处理）
    const isKatabump = task.url.includes('katabump');
    
    if (isKatabump) {
      console.log("[taskService] 检测到 KataBump，特殊处理 Cloudflare 验证");
      // KataBump 的 cf_clearance 绑定 User-Agent + IP，直接注入无效
      // 方案：先访问首页让 Cloudflare 验证通过，再跳转到目标页面
      try {
        // 第 1 步：访问首页，让 Cloudflare 验证
        console.log("[taskService] 第 1 步：访问 KataBump 首页过 CF");
        await page.goto("https://dashboard.katabump.com/dashboard", { 
          waitUntil: "domcontentloaded", 
          timeout: 30000 
        }).catch((e: any) => console.log("[taskService] 首页访问:", e.message));
        
        // 等 Cloudflare 验证通过
        await sleep(8000);
        
        // 检测是否还在 CF 验证页
        const isCF = await page.evaluate(() => {
          const t = document.body?.innerText || "";
          return t.includes("Just a moment") || t.includes("请验证你是真人") || 
                 t.includes("Verify you are human") || t.includes("challenge-platform");
        }).catch(() => false);
        
        if (isCF) {
          console.log("[taskService] CF 验证页，等待自动通过...");
          for (let i = 0; i < 15; i++) {
            await sleep(3000);
            const stillCF = await page.evaluate(() => {
              const t = document.body?.innerText || "";
              return t.includes("Just a moment") || t.includes("challenge-platform");
            }).catch(() => false);
            if (!stillCF) {
              console.log("[taskService] ✅ CF 验证通过");
              break;
            }
          }
        }
        
        // 第 2 步：访问目标页面
        console.log("[taskService] 第 2 步：访问目标页面");
        await page.goto(task.url, { waitUntil: "domcontentloaded", timeout: 30000 })
          .catch((e: any) => console.log("[taskService] 目标页面:", e.message));
        await sleep(5000);
        
      } catch (e: any) {
        console.log("[taskService] KataBump 特殊处理异常:", e.message);
      }
    } else {
      // 其他网站正常访问
      try {
        await page.goto(task.url, { waitUntil: "load", timeout: 60000 });
      } catch (e: any) {
        console.log("[taskService] page.goto 超时，继续:", e.message);
      }
      await sleep(10000);
    }

    // 检测 CF 验证页
    const isCFPage = await page.evaluate(() => {
      const text = document.body.innerText || "";
      return text.includes("Just a moment") || text.includes("请验证你是真人") ||
             text.includes("Verify you are human") || text.includes("正在进行安全验证");
    }).catch(() => false);

    if (isCFPage) {
      console.log("[taskService] 检测到 CF 验证页，尝试通过...");
      // 等 CF 自动通过（最多 60 秒）
      for (let i = 0; i < 20; i++) {
        await sleep(3000);
        const stillCF = await page.evaluate(() => {
          const text = document.body.innerText || "";
          return text.includes("Just a moment") || text.includes("请验证你是真人") || text.includes("Verify you are human");
        }).catch(() => false);
        if (!stillCF) {
          console.log("[taskService] ✅ CF 验证通过");
          break;
        }
        // 尝试点击复选框
        try {
          const iframe = page.frameLocator("iframe[src*='challenges.cloudflare.com']").first();
          await iframe.locator("input[type='checkbox'], body").first().click({ timeout: 3000 }).catch(() => {});
        } catch {}
      }
      await sleep(3000);
    }

    // 提取剩余时间
    const pageText = await page.evaluate(() => document.body.innerText).catch(() => "");
    const remainingTime = extractRemainingTime(pageText);
    if (remainingTime) console.log(`[taskService] ⏰ 剩余时间: ${remainingTime}`);

    // 点击续期按钮（如果配置了）
    let renewMsg = "";
    let loopResultMsg = "";
    if (task.renewButtonText && task.renewButtonText.trim()) {
      console.log(`[taskService] 查找续期按钮: "${task.renewButtonText}"`);
      // 模拟人类阅读页面：等待 3-5 秒后再点击
      await sleep(3000 + Math.random() * 2000);
      await sleep(2000);

      const buttonText = task.renewButtonText.trim();
      let clicked = await clickButtonOnce(page, buttonText);
      if (clicked) console.log("[taskService] ✅ 首次点击成功");

      renewMsg = clicked ? ` | 已点击按钮 "${buttonText}"` : ` | 未找到按钮 "${buttonText}"`;

      if (clicked) {
        // 等待页面响应
        try { await page.waitForLoadState("networkidle", { timeout: 8000 }); } catch {}
        await sleep(2000);

        // ============================================
        // 处理 Turnstile 验证弹窗 (gaming4free 专用)
        // 点击 +90 min 后会弹出 #g4f-ts-modal 验证窗口
        // 在 stealth 模式下 Turnstile 通常会自动通过
        // ============================================
        const tsPassed = await handleTurnstileCaptcha(page, 60000);
        if (!tsPassed) {
          renewMsg += ` | ⚠️ Turnstile 验证未通过`;
          console.log("[taskService] ⚠️ Turnstile 验证未通过，继续检查页面状态");
        }
        await sleep(3000);

        // 检查 CF 验证弹窗（点击后可能弹出，旧逻辑保留）
        const cfAfter = await page.evaluate(() => {
          const text = document.body.innerText || "";
          return text.includes("Just a moment") || text.includes("Verify you are human") || text.includes("正在验证");
        }).catch(() => false);

        if (cfAfter) {
          console.log("[taskService] 点击后出现 CF 验证，等待通过...");
          for (let i = 0; i < 15; i++) {
            await sleep(3000);
            const stillCF = await page.evaluate(() => {
              const text = document.body.innerText || "";
              return text.includes("正在验证") || text.includes("Verifying");
            }).catch(() => false);
            if (!stillCF) break;
          }
          await sleep(2000);
        }

        // 重新提取剩余时间
        const newPageText = await page.evaluate(() => document.body.innerText).catch(() => "");
        const newRemaining = extractRemainingTime(newPageText);
        if (newRemaining) {
          renewMsg += ` | 新剩余时间: ${newRemaining}`;
        }

        // ============================================
        // 循环点击模式（gaming4free 的 +90min 按钮专用）
        // 点击后 4 分钟冷却，可重复点击，上限 48 小时
        // 配置在 customScript 字段：LOOP_MODE:1 COOLDOWN_SEC:240 CAP_HOURS:48 MAX_CLICKS:35
        // ============================================
        const loopCfg = extractLoopConfig(task.customScript || "");
        if (loopCfg.enabled) {
          console.log(`[taskService] 🔁 进入循环点击模式: 冷却=${loopCfg.cooldownSec}s, 上限=${loopCfg.capHours}h, 最多点击=${loopCfg.maxClicks}次`);
          let successClicks = 1;  // 首次点击已成功
          let capped = false;

          for (let i = 1; i < loopCfg.maxClicks; i++) {
            // 1. 检查当前剩余时间，若已达上限，停止
            try {
              const curText = await page.evaluate(() => document.body.innerText).catch(() => "");
              const curRemain = extractRemainingTime(curText) || "";
              const curMins = parseRemainingMinutes(curRemain);
              if (curMins !== null && curMins >= loopCfg.capHours * 60 - 5) {
                console.log(`[taskService] 🛑 已达时间上限 ${loopCfg.capHours}h (当前 ${curMins} 分钟), 停止循环`);
                loopResultMsg = ` | 循环点击 ${successClicks} 次后达上限 ${loopCfg.capHours}h`;
                capped = true;
                break;
              }
            } catch {}

            // 2. 等待冷却（每 30 秒检测一次按钮状态，提前恢复就提前点击）
            console.log(`[taskService] ⏳ 等待冷却 ${loopCfg.cooldownSec}秒 (第 ${i + 1}/${loopCfg.maxClicks} 轮)...`);
            const cooldownEnd = Date.now() + loopCfg.cooldownSec * 1000;
            let cooldownDone = false;
            while (Date.now() < cooldownEnd) {
              await sleep(30000);  // 每 30 秒检测一次
              const btnState = await checkButtonState(page, buttonText);
              if (btnState === 'clickable') {
                console.log(`[taskService] ✅ 按钮已恢复可点击 (冷却提前结束)`);
                cooldownDone = true;
                break;
              }
              if (btnState === 'capped') {
                console.log(`[taskService] 🛑 检测到已达时间上限，停止循环`);
                loopResultMsg = ` | 循环点击 ${successClicks} 次后达上限 ${loopCfg.capHours}h`;
                capped = true;
                break;
              }
              // 'cooldown' 或 'missing' 状态都继续等
              // 'cooldown' = 按钮在冷却中（被倒计时替换），正常
              // 'missing' = 找不到按钮也找不到冷却指示，可能页面加载慢，再等等
            }
            if (capped) break;
            if (!cooldownDone) {
              // 等够冷却时间，最后再检查一次
              const btnState = await checkButtonState(page, buttonText);
              if (btnState === 'capped') {
                loopResultMsg = ` | 循环点击 ${successClicks} 次后达上限 ${loopCfg.capHours}h`;
                capped = true;
                break;
              }
              if (btnState !== 'clickable') {
                console.log(`[taskService] 按钮状态: ${btnState}, 冷却时间已到，再等 30 秒...`);
                // 即使状态不是 clickable，冷却时间已到，再等 30 秒后强制尝试点击
                await sleep(30000);
              }
            }

            // 3. 再次点击
            const clickedAgain = await clickButtonOnce(page, buttonText);
            if (clickedAgain) {
              successClicks++;
              console.log(`[taskService] ✅ 第 ${successClicks} 次点击成功`);
              // 等待页面响应
              try { await page.waitForLoadState("networkidle", { timeout: 8000 }); } catch {}
              await sleep(2000);

              // 处理 Turnstile 验证（每次点击后都可能弹出）
              const tsPassed2 = await handleTurnstileCaptcha(page, 60000);
              if (!tsPassed2) {
                console.log("[taskService] ⚠️ 循环点击后 Turnstile 验证未通过");
              }
              await sleep(3000);

              // 检查 CF
              const cfCheck = await page.evaluate(() => {
                const t = document.body.innerText || "";
                return t.includes("Just a moment") || t.includes("Verify you are human") || t.includes("正在验证");
              }).catch(() => false);
              if (cfCheck) {
                console.log("[taskService] 循环点击后出现 CF 验证，等待通过...");
                for (let j = 0; j < 15; j++) {
                  await sleep(3000);
                  const stillCF = await page.evaluate(() => {
                    const t = document.body.innerText || "";
                    return t.includes("正在验证") || t.includes("Verifying");
                  }).catch(() => false);
                  if (!stillCF) break;
                }
                await sleep(2000);
              }

              // 4. 再次检查上限
              try {
                const afterText = await page.evaluate(() => document.body.innerText).catch(() => "");
                const afterRemain = extractRemainingTime(afterText) || "";
                const afterMins = parseRemainingMinutes(afterRemain);
                if (afterMins !== null && afterMins >= loopCfg.capHours * 60 - 5) {
                  console.log(`[taskService] 🛑 已达时间上限 ${loopCfg.capHours}h (当前 ${afterMins} 分钟), 停止循环`);
                  loopResultMsg = ` | 循环点击 ${successClicks} 次后达上限 ${loopCfg.capHours}h`;
                  capped = true;
                  break;
                }
              } catch {}
            } else {
              console.log(`[taskService] ⚠️ 第 ${i + 1} 轮点击失败，停止循环`);
              loopResultMsg = ` | 循环点击 ${successClicks} 次后按钮不可点`;
              break;
            }
          }

          if (!loopResultMsg) {
            loopResultMsg = ` | 循环点击完成，共点击 ${successClicks} 次`;
          }
          console.log(`[taskService] 🔁 循环结束: ${loopResultMsg}`);
        }
      }
    }

    if (loopResultMsg) renewMsg += loopResultMsg;

    screenshot = (await page.screenshot({ fullPage: false, type: "jpeg", quality: 60 })).toString("base64");

    // 成功关键词验证
    const successKeyword = extractSuccessKeyword(task.customScript || "");
    if (successKeyword) {
      const finalText = await page.evaluate(() => document.body.innerText).catch(() => "");
      const matched = successKeyword.find(kw => finalText.includes(kw));
      if (matched) {
        return { success: true, msg: `签到成功 | ✅ 验证关键词 "${matched}"${renewMsg}`, screenshot, remainingTime: remainingTime || undefined };
      }
      return { success: false, msg: `未检测到成功关键词 [${successKeyword.join("|")}]${renewMsg}`, screenshot, remainingTime: remainingTime || undefined };
    }

    // 没有 SUCCESS_KEYWORD 时，检查 Turnstile 是否真的通过
    // 如果有 renewMsg 包含"验证未通过"或"failure_retry"，判定为失败
    if (renewMsg.includes("验证未通过") || renewMsg.includes("failure_retry") || renewMsg.includes("验证失败")) {
      return { success: false, msg: `续期失败 | Turnstile 验证未通过${renewMsg}`, screenshot, remainingTime: remainingTime || undefined };
    }

    // 如果有续期按钮但 Turnstile 没有明确通过，检查时间是否增加
    if (task.renewButtonText && task.renewButtonText.trim()) {
      // 检查剩余时间是否增加了（说明真的续期成功）
      const finalText = await page.evaluate(() => document.body.innerText).catch(() => "");
      const finalRemaining = extractRemainingTime(finalText);
      if (finalRemaining) {
        renewMsg += ` | 最终剩余时间: ${finalRemaining}`;
        // 如果能提取到时间，说明页面正常，但无法确定是否真的续期
        // 保守判断：如果有循环点击且至少点了 1 次，就算成功
        if (loopResultMsg && loopResultMsg.includes("点击")) {
          return { success: true, msg: `签到成功${renewMsg}`, screenshot, remainingTime: finalRemaining };
        }
        // 没有循环点击，检查时间是否比初始时间多
        // 无法准确判断，保守返回成功
        return { success: true, msg: `签到成功${renewMsg}`, screenshot, remainingTime: finalRemaining };
      }
    }

    return { success: true, msg: `签到成功${renewMsg}`, screenshot, remainingTime: remainingTime || undefined };
  } catch (e: any) {
    console.error(`[taskService] Playwright 异常: ${e.message}`);
    return { success: false, msg: `执行异常: ${e.message}` };
  } finally {
    if (browser) {
      try { await browser.close(); console.log("[taskService] 浏览器已关闭"); } catch {}
    }
  }
}

export { solveCaptcha } from "./_core/freeCaptcha";
