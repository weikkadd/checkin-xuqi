import { getSystemConfig } from "../db";
import https from "https";
import http from "http";

// Telegram 通知模块 - 简洁卡片 + 4 个功能按钮 + 站点可点击链接

interface TaskInfo {
  id: number;
  name: string;
  url?: string | null;
}

interface NotifyOptions {
  disableNotification?: boolean;
}

const PANEL_URL = "https://checkin-new-panel.pages.dev";

// Telegram API 基础 URL（通过 CF Worker 代理）
const TG_API_BASE = process.env.TG_API_PROXY || "http://tg-proxy.weissdadqq.workers.dev";

function escapeHtml(text: string): string {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// 获取域名（用于显示）
function shortDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url || "";
  }
}

// 生成可点击的站点链接
// 显示域名，点击跳转到完整 URL
function siteLink(url: string | null | undefined): string {
  if (!url) return "—";
  const domain = shortDomain(url);
  return `<a href="${escapeHtml(url)}">${escapeHtml(domain)}</a>`;
}

// 自动识别任务名称
// 优先用面板上设置的任务名（task.name），如果为空才从 URL 提取
function autoTaskName(task: TaskInfo): string {
  if (task.name && task.name.trim()) return task.name;
  if (!task.url) return task.name || "未知任务";
  try {
    const url = new URL(task.url);
    let host = url.hostname.replace(/^www\./, "");
    const parts = host.split(".");
    if (parts.length >= 2) return parts[parts.length - 2];
    return host;
  } catch {
    return task.name || "未知任务";
  }
}

// TG 按钮布局 - 2x3 网格
function buildTaskKeyboard(task: TaskInfo) {
  return {
    inline_keyboard: [
      [
        { text: "🔄 自动续期", callback_data: `run:${task.id}` },
        { text: "✋ 手动签到", url: task.url || "#" },
      ],
      [
        { text: "🔔 测试通知", callback_data: `test:${task.id}` },
        { text: "📊 查看日志", url: `${PANEL_URL}/?task=${task.id}#logs` },
      ],
      [
        { text: "✏️ 编辑任务", url: `${PANEL_URL}/?task=${task.id}#edit` },
        { text: "🌐 打开面板", url: PANEL_URL },
      ],
    ],
  };
}

// 签到成功
export async function notifyTaskSuccess(
  task: TaskInfo,
  nextTime: string,
  duration?: number,
  options?: NotifyOptions,
  remainingTime?: string
) {
  const cfg = await getSystemConfig();
  if (!cfg.tgBotToken || !cfg.tgChatId) return;

  const dur = duration ? `${Math.round(duration / 1000)}秒` : "—";

  let text = `<b>✓ 签到成功</b>
任务名称：${escapeHtml(autoTaskName(task))}
下次签到：${escapeHtml(nextTime)}
计时：${dur}
站点：${siteLink(task.url)}`;
  if (remainingTime) {
    text += `\n⏰ 剩余时间：${escapeHtml(remainingTime)}`;
  }
  text += `\n自动续期已完成`;

  await sendTgMsg(cfg.tgBotToken, cfg.tgChatId, text, buildTaskKeyboard(task), options);
}

// 签到失败
export async function notifyTaskFail(
  task: TaskInfo,
  errMsg: string,
  duration?: number,
  options?: NotifyOptions,
  remainingTime?: string
) {
  const cfg = await getSystemConfig();
  if (!cfg.tgBotToken || !cfg.tgChatId) return;

  const dur = duration ? `${Math.round(duration / 1000)}秒` : "—";
  const firstLine = (errMsg || "").split("\n")[0].substring(0, 120);

  let text = `<b>✗ 签到失败</b>
任务名称：${escapeHtml(autoTaskName(task))}
计时：${dur}
站点：${siteLink(task.url)}`;
  if (remainingTime) {
    text += `\n⏰ 剩余时间：${escapeHtml(remainingTime)}`;
  }
  text += `\n错误：${escapeHtml(firstLine)}`;

  await sendTgMsg(cfg.tgBotToken, cfg.tgChatId, text, buildTaskKeyboard(task), options);
}

// 即将到期
export async function notifyTaskExpire(
  task: TaskInfo,
  days: number,
  options?: NotifyOptions
) {
  const cfg = await getSystemConfig();
  if (!cfg.tgBotToken || !cfg.tgChatId) return;

  const emoji = days <= 1 ? "🚨" : days <= 3 ? "⚠️" : "⏰";
  const text = `<b>${emoji} 即将到期</b>
任务名称：${escapeHtml(autoTaskName(task))}
剩余：${days} 天
站点：${siteLink(task.url)}
请尽快续期`;

  await sendTgMsg(cfg.tgBotToken, cfg.tgChatId, text, buildTaskKeyboard(task), options);
}

// 测试通知
export async function sendTestNotify(task: TaskInfo) {
  const cfg = await getSystemConfig();
  if (!cfg.tgBotToken || !cfg.tgChatId) return;

  const text = `<b>🔔 测试通知</b>
任务名称：${escapeHtml(autoTaskName(task))}
站点：${siteLink(task.url)}
推送通道正常`;

  await sendTgMsg(cfg.tgBotToken, cfg.tgChatId, text, buildTaskKeyboard(task));
}

// 按钮触发的执行结果反馈
export async function notifyCallbackResult(
  task: TaskInfo,
  action: "run" | "test",
  result: { success: boolean; msg: string }
) {
  const cfg = await getSystemConfig();
  if (!cfg.tgBotToken || !cfg.tgChatId) return;

  const actionText = action === "run" ? "执行" : "测试";
  const emoji = result.success ? "✓" : "✗";
  const firstLine = (result.msg || "").split("\n")[0].substring(0, 120);

  const text = `<b>${emoji} ${actionText}完成</b>
任务名称：${escapeHtml(autoTaskName(task))}
站点：${siteLink(task.url)}
结果：${escapeHtml(firstLine)}`;

  await sendTgMsg(cfg.tgBotToken, cfg.tgChatId, text, buildTaskKeyboard(task));
}

/**
 * 用 node:http/https 模块发请求（根据 URL 协议自动选择）
 * 替代 fetch，避免 HF Space fetch 挂起 + TLS 握手失败
 */
function tgHttpRequest(url: string, options: { method: string; headers: any; body?: string }, timeoutMs = 10000): Promise<{ status: number; data: string }> {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const isHttps = urlObj.protocol === "https:";
    const req = (isHttps ? https : http).request({
      hostname: urlObj.hostname,
      port: urlObj.port || (isHttps ? 443 : 80),
      path: urlObj.pathname + urlObj.search,
      method: options.method,
      headers: options.headers,
      timeout: timeoutMs,
    }, (resp) => {
      let data = "";
      resp.on("data", chunk => data += chunk);
      resp.on("end", () => resolve({ status: resp.statusCode || 0, data }));
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function sendTgMsg(
  token: string,
  chatId: string,
  text: string,
  replyMarkup?: any,
  options?: NotifyOptions
) {
  const body: any = {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
    disable_notification: options?.disableNotification ?? false,
  };
  if (replyMarkup) {
    body.reply_markup = replyMarkup;
  }

  const bodyStr = JSON.stringify(body);
  const url = `${TG_API_BASE}/bot${token}/sendMessage`;

  // 最多重试 3 次
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      console.log(`[TG sendTgMsg] 发送请求 (attempt ${attempt})`);
      const resp = await tgHttpRequest(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(bodyStr) },
        body: bodyStr,
      }, 10000);

      const data = JSON.parse(resp.data);
      if (data.ok) {
        console.log(`[TG sendTgMsg] ✅ 发送成功 (attempt ${attempt})`);
        return;
      } else {
        console.error(`[TG sendTgMsg] ❌ API 错误 (attempt ${attempt}):`, data.description);
        if (attempt < 3) await new Promise(r => setTimeout(r, 2000 * attempt));
      }
    } catch (e: any) {
      console.error(`[TG sendTgMsg] 异常 (attempt ${attempt}):`, e.message);
      if (attempt < 3) await new Promise(r => setTimeout(r, 2000 * attempt));
    }
  }
  console.error("[TG sendTgMsg] ❌ 3 次重试均失败");
}
