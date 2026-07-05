import dotenv from "dotenv";
dotenv.config();

// 设置时区为北京时间（HF Spaces 默认是 UTC，需要手动设置）
// 这样 console.log 和 Date 都会用北京时间
process.env.TZ = process.env.TZ || "Asia/Shanghai";

import express from "express";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { CronJob } from "cron";
import { appRouter } from "./_core/trpc";
import { createContext } from "./_core/trpc";
import { runTaskCheckAll, runSingleTask, getTaskById, testTaskAlert } from "./db";
import https from "https";
import http from "http";

const app = express();
const PORT = process.env.PORT || 3000;

// Telegram API 基础 URL（通过 CF Worker 代理）
const TG_API_BASE = process.env.TG_API_PROXY || "http://tg-proxy.weissdadqq.workers.dev";

// 用 node:https/http 模块发请求（替代 fetch，避免 HF Space fetch 挂起）
function tgRequest(path: string, method: string = "GET", body?: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const fullUrl = `${TG_API_BASE}${path}`;
    const url = new URL(fullUrl);
    const isHttps = url.protocol === "https:";
    const bodyStr = body ? JSON.stringify(body) : undefined;
    const options = {
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: url.pathname + url.search,
      method,
      headers: bodyStr ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(bodyStr) } : {},
      timeout: 10000,
    };
    const req = (isHttps ? https : http).request(options, (resp) => {
      let data = "";
      resp.on("data", chunk => data += chunk);
      resp.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve({ ok: false, description: "JSON parse error" }); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
    if (bodyStr) req.write(bodyStr);
    req.end();
  });
}

// 1. 解析 JSON 请求体
app.use(express.json());

// 2. 全局跨域中间件（必须放在所有路由前面，CF Pages 前端正常跨域）
// 注意：Access-Control-Allow-Headers 必须包含 Authorization
// 因为前端 task.create/update/delete 等接口需要在请求头带 Authorization: Bearer xxx
// 浏览器遇到非简单 header 会发 OPTIONS 预检，预检失败就报 "Failed to fetch"
app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", "*");
  res.header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS");
  res.header("Access-Control-Allow-Headers", "Content-Type, Authorization");
  if (req.method === "OPTIONS") return res.sendStatus(200);
  next();
});

// 3. tRPC 接口路由
app.use(
  "/trpc",
  createExpressMiddleware({
    router: appRouter,
    createContext,
  })
);

// 4. 健康检测接口
app.get("/ping", (req, res) => {
  res.send("ok");
});

// 5. 根路径欢迎页
app.get("/", (req, res) => {
  res.send(`
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Checkin New Panel API</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; line-height: 1.6; }
    h1 { color: #10b981; }
    .info { background: #1e293b; padding: 20px; border-radius: 8px; margin: 20px 0; }
    code { background: #334155; padding: 2px 6px; border-radius: 4px; color: #fbbf24; }
    a { color: #60a5fa; }
  </style>
</head>
<body>
  <h1>🎮 Checkin New Panel API</h1>
  <p>HuggingFace Spaces 后端服务已启动 ✅</p>
  <div class="info">
    <p><strong>tRPC 端点:</strong> <code>/trpc</code></p>
    <p><strong>健康检查:</strong> <code>/ping</code></p>
    <p><strong>Telegram Webhook:</strong> <code>/tg/webhook</code></p>
    <p><strong>TG 测试:</strong> <a href="/tg-test"><code>/tg-test</code></a></p>
    <p><strong>当前时间:</strong> ${new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</p>
  </div>
  <p>前端面板: <a href="https://checkin-new-panel.pages.dev">checkin-new-panel.pages.dev</a></p>
</body>
</html>
  `);
});

// 5.5 TG 测试接口 - 测试后端是否能访问 Telegram API
app.get("/tg-test", async (req, res) => {
  const token = process.env.TG_BOT_TOKEN;
  const chatId = process.env.TG_CHAT_ID;

  const result = {
    envCheck: {
      TG_BOT_TOKEN: token ? `已设置 (${token.substring(0, 8)}...)` : "❌ 未设置",
      TG_CHAT_ID: chatId || "❌ 未设置",
    },
    fetchTest: null as any,
    sendTest: null as any,
  };

  // 测试 1: 能否访问 Telegram API
  try {
    const data = await tgRequest(`/bot${token}/getMe`);
    result.fetchTest = {
      success: data.ok,
      botName: data.result?.first_name,
      botUsername: data.result?.username,
      error: data.ok ? null : data.description,
    };
  } catch (e: any) {
    result.fetchTest = { success: false, error: e.message };
  }

  // 测试 2: 能否发消息到群
  try {
    const data = await tgRequest(`/bot${token}/sendMessage`, "POST", {
      chat_id: chatId,
      text: "🔧 TG 测试接口发的消息\n\n如果你看到这条消息，说明后端能正常发到群",
      disable_web_page_preview: true,
    });
    result.sendTest = {
      success: data.ok,
      messageId: data.result?.message_id,
      error: data.ok ? null : data.description,
    };
  } catch (e: any) {
    result.sendTest = { success: false, error: e.message };
  }

  res.json(result);
});

// 6. Telegram Webhook - 接收群里按钮点击的 callback_query
// 当用户在群里点"立即执行"/"测试通知"按钮时，Telegram 会发请求到这里
app.post("/tg/webhook", async (req, res) => {
  console.log("[TG Webhook] 收到请求:", JSON.stringify(req.body).substring(0, 200));

  try {
    const update = req.body;
    const callbackQuery = update?.callback_query;

    if (!callbackQuery) {
      console.log("[TG Webhook] 不是 callback_query，忽略");
      return res.json({ ok: true });
    }

    const { id: queryId, data, message } = callbackQuery;
    console.log(`[TG Webhook] 收到 callback: data=${data}, queryId=${queryId}`);

    // 解析 callback_data，格式: action:taskId (如 "run:1", "test:1")
    const [action, taskIdStr] = (data || "").split(":");
    const taskId = parseInt(taskIdStr, 10);

    if (!taskId || isNaN(taskId)) {
      console.log(`[TG Webhook] 任务 ID 无效: ${taskIdStr}`);
      await answerCallbackQuery(queryId, "❌ 任务 ID 无效");
      return res.json({ ok: true });
    }

    console.log(`[TG Webhook] 查询任务 id=${taskId}`);
    const task = await getTaskById(taskId);
    if (!task) {
      console.log(`[TG Webhook] 任务不存在: ${taskId}`);
      await answerCallbackQuery(queryId, "❌ 任务不存在");
      return res.json({ ok: true });
    }
    console.log(`[TG Webhook] 找到任务: ${task.name}`);

    // 检查环境变量
    const token = process.env.TG_BOT_TOKEN;
    const chatId = process.env.TG_CHAT_ID;
    console.log(`[TG Webhook] 环境变量: TG_BOT_TOKEN=${token ? "已设置(" + token.substring(0, 8) + "...)" : "未设置"}, TG_CHAT_ID=${chatId || "未设置"}`);

    // 先回复 Telegram（必须在 30 秒内回复，否则按钮会一直转圈）
    const actionText = action === "run" ? "自动续期" : action === "test" ? "测试通知" : action;
    const alertText = `⏳ 正在${actionText}任务 ${task.name}...`;
    console.log(`[TG Webhook] 回复 callback: ${alertText}`);
    await answerCallbackQuery(queryId, alertText);

    // 异步执行任务，避免阻塞 webhook 响应
    console.log(`[TG Webhook] 开始异步执行 action=${action}`);
    (async () => {
      try {
        if (action === "run") {
          console.log(`[TG Webhook] 触发自动续期: ${task.name} (id=${taskId})`);
          // runSingleTask 内部会发 TG 通知（成功/失败），不需要额外发
          const result = await runSingleTask(taskId);
          console.log(`[TG Webhook] 任务执行完成: success=${result.success}`);
        } else if (action === "test") {
          console.log(`[TG Webhook] 触发测试通知: ${task.name} (id=${taskId})`);
          await testTaskAlert(taskId);
          console.log(`[TG Webhook] 测试通知已发送`);
        } else {
          console.log(`[TG Webhook] 未知 action: ${action}`);
        }
      } catch (e: any) {
        console.error(`[TG Webhook] 执行失败:`, e.message);
        console.error(`[TG Webhook] 错误堆栈:`, e.stack);
      }
    })();

    return res.json({ ok: true });
  } catch (e: any) {
    console.error("[TG Webhook] 处理失败:", e.message);
    console.error("[TG Webhook] 错误堆栈:", e.stack);
    return res.status(500).json({ ok: false, error: e.message });
  }
});

// 回复 callback_query（让按钮停止转圈）
async function answerCallbackQuery(callbackQueryId: string, text: string) {
  const token = process.env.TG_BOT_TOKEN;
  if (!token) {
    console.error("[TG] answerCallbackQuery 失败: TG_BOT_TOKEN 未设置");
    return;
  }
  try {
    const data = await tgRequest(`/bot${token}/answerCallbackQuery`, "POST", {
      callback_query_id: callbackQueryId,
      text,
      show_alert: false,
    });
    if (data.ok) {
      console.log(`[TG] answerCallbackQuery 成功: ${text}`);
    } else {
      console.error(`[TG] answerCallbackQuery 失败:`, data.description);
    }
  } catch (e: any) {
    console.error("[TG] answerCallbackQuery 异常:", e.message);
  }
}

// 定时签到任务 - 支持每任务独立 Cron（多账号错开执行）
const globalCronExpr = process.env.GLOBAL_CRON || "0 0 */6 * * *";
console.log(`全局签到定时任务已启动，表达式: ${globalCronExpr}`);
const cronJobs: any[] = [];

// 初始化任务级 Cron（启动时执行一次）
async function initTaskCrons() {
  // 先停掉旧的
  for (const job of cronJobs) {
    try { job.stop(); } catch {}
  }
  cronJobs.length = 0;

  try {
    const { getTaskCronGroups } = require("./db");
    const groups = await getTaskCronGroups();
    console.log(`[Cron] 任务分组: ${groups.size} 个不同 Cron 表达式`);
    for (const [cron, taskIds] of groups.entries()) {
      console.log(`[Cron] 表达式 "${cron}" -> 任务 ID: [${taskIds.join(", ")}]`);
      const job = new CronJob(
        cron,
        async () => {
          console.log(`[Cron] 触发表达式 "${cron}", 执行 ${taskIds.length} 个任务`);
          for (const taskId of taskIds) {
            try {
              await runSingleTask(taskId);
            } catch (e) {
              console.error(`[Cron] 任务 ${taskId} 执行异常:`, e);
            }
          }
        },
        null,
        true,
        "Asia/Shanghai"
      );
      cronJobs.push(job);
    }
  } catch (e: any) {
    console.error("[Cron] 初始化任务级 Cron 失败，回退到全局 Cron:", e.message);
    // 回退：用全局 Cron 跑所有到期任务
    new CronJob(
      globalCronExpr,
      async () => {
        console.log("开始批量执行所有到期签到任务");
        try {
          await runTaskCheckAll();
          console.log("本轮批量签到任务执行完毕");
        } catch (err) {
          console.error("批量签到执行异常:", err);
        }
      },
      null,
      true,
      "Asia/Shanghai"
    );
  }
}

// 启动 5 秒后初始化任务级 Cron（等数据库连接好）
setTimeout(() => {
  initTaskCrons().catch(e => console.error("[Cron] 初始化异常:", e));
}, 5000);

// 提供重新初始化 Cron 的接口（前端修改任务后调用）
app.get("/reload-cron", async (req, res) => {
  try {
    await initTaskCrons();
    res.json({ ok: true, msg: "Cron 已重新加载" });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// 启动监听
app.get("/net-test", async (req, res) => {
  const results: any = {};
  try {
    const r = await fetch("https://tg-proxy.weissdadqq.workers.dev/ping");
    results.cfWorker = { status: r.status, ok: true };
  } catch (e: any) {
    results.cfWorker = { error: e.message };
  }
  try {
    const r = await fetch("https://api.telegram.org/bot8644834310:AAE6rSjWQnleoVoK591aECEZss60aMqS5dw/getMe");
    results.telegram = { status: r.status, ok: true };
  } catch (e: any) {
    results.telegram = { error: e.message };
  }
  try {
    const { lookup } = await import("dns").then(m => m.promises);
    const addr = await lookup("tg-proxy.weissdadqq.workers.dev");
    results.dns = { address: addr.address };
  } catch (e: any) {
    results.dns = { error: e.message };
  }
  try {
    const https = await import("https");
    const data: any = await new Promise((resolve, reject) => {
      https.get("https://tg-proxy.weissdadqq.workers.dev/ping", (resp) => {
        let d = "";
        resp.on("data", c => d += c);
        resp.on("end", () => resolve({ status: resp.statusCode, body: d }));
      }).on("error", reject);
    });
    results.httpsModule = data;
  } catch (e: any) {
    results.httpsModule = { error: e.message };
  }
  res.json(results);
});
app.listen(PORT, () => {
  console.log(`服务运行在端口: ${PORT}`);
});

export type AppRouter = typeof appRouter;
