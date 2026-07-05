import { drizzle } from "drizzle-orm/mysql2";
import mysql from "mysql2/promise";
import { tasks, adminUser, taskLog } from "../drizzle/schema";
import { eq, lte, sql, desc } from "drizzle-orm";
import { manualRunTask } from "./taskService";
import dotenv from "dotenv";
dotenv.config();

/**
 * 从剩余时间字符串解析出未来的 Date
 * 支持格式：
 *   "07:59:53" → 现在 + 7小时59分53秒
 *   "14:31:55" → 现在 + 14小时31分55秒
 *   "07:44:35" → 现在 + 7小时44分35秒
 *   "到期: 2026/07/09 14:45:38" → 直接解析日期
 *   "7 天" → 现在 + 7天
 */
function parseRemainingTimeToDate(timeStr: string): Date | null {
  if (!timeStr) return null;

  // 格式 1: 到期: YYYY/MM/DD HH:MM:SS
  let m = timeStr.match(/到期[:\s]*([\d\/\s:]+)/);
  if (m) {
    const d = new Date(m[1].trim().replace(/\//g, "-"));
    if (!isNaN(d.getTime())) return d;
  }

  // 格式 2: HH:MM:SS（剩余时间）
  m = timeStr.match(/^(\d{1,2}):(\d{2}):(\d{2})/);
  if (m) {
    const hours = parseInt(m[1], 10);
    const mins = parseInt(m[2], 10);
    const secs = parseInt(m[3], 10);
    const d = new Date();
    d.setHours(d.getHours() + hours);
    d.setMinutes(d.getMinutes() + mins);
    d.setSeconds(d.getSeconds() + secs);
    return d;
  }

  // 格式 3: N 天
  m = timeStr.match(/(\d+)\s*天/);
  if (m) {
    const d = new Date();
    d.setDate(d.getDate() + parseInt(m[1], 10));
    return d;
  }

  return null;
}

// 解析 DATABASE_URL，兼容多种 ssl 参数写法
// Render 配的 URL 可能是:
//   ...?ssl={"rejectUnauthorized":true}      ← JSON 字符串（花括号未编码，会出错）
//   ...?ssl=%7B%22rejectUnauthorized%22%3Atrue%7D  ← URL 编码的 JSON
//   ...?ssl=true                            ← 简单布尔值
// 这里统一处理：剥离 ssl= 参数，由代码里直接传 ssl 对象给 mysql2
function parseDbConfig(rawUrl: string) {
  let url = rawUrl;
  // 移除 url 里所有形式的 ssl= 参数，由代码内统一注入
  url = url.replace(/[?&]ssl=[^&]*/g, "");
  // 如果原本以 ? 结尾，去掉 ?
  url = url.replace(/\?$/, "");
  return url;
}

const cleanUrl = parseDbConfig(process.env.DATABASE_URL || "");

console.log("[DB] 连接 TiDB:", cleanUrl.replace(/:[^:@]+@/, ":***@"));

const pool = mysql.createPool({
  uri: cleanUrl,
  ssl: { rejectUnauthorized: false },
  // 显式允许 TiDB Cloud 的自签名证书
  connectionLimit: 5,
  connectTimeout: 30000,
});
export const db = drizzle(pool);

// 启动时测一下连接
pool.getConnection().then(conn => {
  conn.query("SELECT 1").then(() => {
    console.log("[DB] ✅ 数据库连接测试成功");
    conn.release();
  }).catch(err => {
    console.error("[DB] ❌ 数据库查询测试失败:", err.message);
    conn.release();
  });
}).catch(err => {
  console.error("[DB] ❌ 数据库连接失败:", err.code, "-", err.message);
});

export async function verifyAdmin(username: string, password: string) {
  const res = await db.select().from(adminUser).where(eq(adminUser.username, username));
  if (res.length === 0) return false;
  return res[0].password === password;
}

export async function getAllTasks() {
  return await db.select().from(tasks).orderBy(tasks.nextRenew);
}

export async function getTaskById(id: number) {
  const res = await db.select().from(tasks).where(eq(tasks.id, id));
  return res[0] ?? null;
}

export async function createTask(data: {
  name: string;
  url: string;
  username?: string;
  password?: string;
  renewCycle: number;
  alertDays: number;
  taskType?: string;
  customScript?: string;
  renewButtonText?: string;
  cookies?: string;
  renewThresholdMinutes?: number;
  execMode?: number;
  cronExpr?: string;
  enabled: boolean;
  shareLink?: string;
}) {
  const nextRenew = new Date();
  nextRenew.setDate(nextRenew.getDate() + data.renewCycle);
  const insertRes = await db.insert(tasks).values({
    ...data,
    nextRenew: nextRenew,
    // 分享链接就是任务的实际签到 URL
    shareLink: data.url,
    lastRenew: null
  });
  return (insertRes as any).insertId;
}

export async function updateTask(id: number, data: Partial<{
  name: string;
  url: string;
  username?: string;
  password?: string;
  renewCycle: number;
  alertDays: number;
  taskType?: string;
  customScript?: string;
  renewButtonText?: string;
  cookies?: string;
  renewThresholdMinutes?: number;
  execMode?: number;
  cronExpr?: string;
  enabled: boolean;
  shareLink?: string;
}>) {
  await db.update(tasks).set(data).where(eq(tasks.id, id));
}

export async function deleteTask(id: number) {
  await db.delete(tasks).where(eq(tasks.id, id));
}

export async function runSingleTask(id: number) {
  const task = await getTaskById(id);
  if (!task) throw new Error("任务不存在");

  const startTime = Date.now();
  let result: { success: boolean; msg: string; screenshot?: string; remainingTime?: string };

  try {
    result = await manualRunTask(task);
  } catch (e: any) {
    result = { success: false, msg: e.message || String(e) };
  }

  const duration = Date.now() - startTime;

  // 记录日志到数据库
  try {
    await db.insert(taskLog).values({
      taskId: task.id,
      taskName: task.name,
      success: result.success,
      errorMsg: result.success ? null : result.msg,
      duration,
      screenshot: result.screenshot || null,
    });
  } catch (e: any) {
    console.error("[DB] 写入 task_log 失败:", e.message);
  }

  // 成功时更新任务的 lastRenew / nextRenew
  if (result.success) {
    const now = new Date();
    let next = new Date();
    next.setDate(next.getDate() + task.renewCycle);

    // 如果页面提取到了剩余时间，用它来计算 nextRenew
    if (result.remainingTime) {
      const parsed = parseRemainingTimeToDate(result.remainingTime);
      if (parsed) {
        next = parsed;
        console.log(`[DB] 从页面剩余时间更新 nextRenew: ${next.toISOString()}`);
      }
    }

    await db.update(tasks)
      .set({ lastRenew: now, nextRenew: next })
      .where(eq(tasks.id, id));

    // 发送 Telegram 成功通知（带任务信息和功能按钮）
    try {
      console.log("[TG] 准备发送成功通知，任务:", task.name);
      const { notifyTaskSuccess } = await import("./_core/tgNotify");
      await notifyTaskSuccess(
        { id: task.id, name: task.name, url: task.url },
        next.toLocaleString("zh-CN"),
        duration,
        undefined,
        result.remainingTime
      );
      console.log("[TG] 成功通知发送完成");
    } catch (e: any) {
      console.error("[TG] 成功通知发送失败:", e.message);
      console.error("[TG] 错误堆栈:", e.stack);
    }
  } else {
    // 失败时发送告警（带任务信息和功能按钮）
    try {
      console.log("[TG] 准备发送失败通知，任务:", task.name);
      const { notifyTaskFail } = await import("./_core/tgNotify");
      await notifyTaskFail(
        { id: task.id, name: task.name, url: task.url },
        result.msg,
        duration,
        undefined,
        result.remainingTime
      );
      console.log("[TG] 失败通知发送完成");
    } catch (e: any) {
      console.error("[TG] 失败通知发送失败:", e.message);
      console.error("[TG] 错误堆栈:", e.stack);
    }
  }

  return result;
}

export async function testTaskAlert(id: number) {
  console.log("[testTaskAlert] 开始，id:", id);
  const task = await getTaskById(id);
  if (!task) {
    console.log("[testTaskAlert] 任务不存在");
    throw new Error("任务不存在");
  }
  console.log("[testTaskAlert] 找到任务:", task.name);
  const { sendTestNotify } = await import("./_core/tgNotify");
  await sendTestNotify({ id: task.id, name: task.name, url: task.url });
  console.log("[testTaskAlert] 完成");
}

// 手动标记签到成功（用户在浏览器手动完成签到后调用）
export async function markManualSuccess(id: number) {
  const task = await getTaskById(id);
  if (!task) throw new Error("任务不存在");

  console.log(`[markManualSuccess] 手动标记成功: ${task.name}`);

  // host2play 等网站用 JS 动态渲染剩余时间，fetch 拿不到
  // 手动签到不 fetch 页面，直接标记成功
  // 剩余时间由用户在浏览器查看，或由自动续期时提取
  const remainingTime: string | undefined = undefined;

  // 更新 lastRenew / nextRenew
  const now = new Date();
  let next = new Date();
  
  // 优先用 cronExpr 计算下次签到时间
  const cronExpr = (task as any).cronExpr;
  if (cronExpr) {
    try {
      const { CronJob } = await import("cron");
      // 获取下一次 Cron 触发时间
      const job = new CronJob(cronExpr, () => {}, null, true, "Asia/Shanghai");
      next = job.nextDate().toJSDate();
      console.log(`[markManualSuccess] 用 cronExpr "${cronExpr}" 计算下次签到: ${next.toISOString()}`);
    } catch (e: any) {
      console.log(`[markManualSuccess] cronExpr 解析失败，用 renewCycle: ${e.message}`);
      next.setDate(next.getDate() + (task.renewCycle || 7));
    }
  } else {
    // 没有 cronExpr，用 renewCycle（天数）
    next.setDate(next.getDate() + (task.renewCycle || 7));
  }

  await db.update(tasks)
    .set({ lastRenew: now, nextRenew: next })
    .where(eq(tasks.id, id));

  // 记录日志
  try {
    await db.insert(taskLog).values({
      taskId: task.id,
      taskName: task.name,
      success: true,
      errorMsg: null,
      duration: 0,
      screenshot: null,
    });
  } catch (e: any) {
    console.error("[DB] 写入 task_log 失败:", e.message);
  }

  // 发送 TG 成功通知
  try {
    const { notifyTaskSuccess } = await import("./_core/tgNotify");
    await notifyTaskSuccess(
      { id: task.id, name: task.name, url: task.url },
      next.toLocaleString("zh-CN"),
      0,
      undefined,
      "手动签到（请在浏览器查看实际时间）"
    );
    console.log("[TG] 手动签到成功通知已发送");
  } catch (e: any) {
    console.error("[TG] 通知发送失败:", e.message);
  }

  return { success: true, msg: "手动签到已标记成功" };
}

export async function runTaskCheckAll() {
  const allTasks = await getAllTasks();
  const now = new Date();
  for (const task of allTasks) {
    if (!task.enabled) continue;
    // execMode=2 是"仅手动"，不参加 Cron 自动执行
    if ((task as any).execMode === 2) continue;
    const nextDate = new Date(task.nextRenew);
    if (nextDate <= now) {
      console.log(`[批量执行] 到期任务: ${task.name}`);
      try {
        await runSingleTask(task.id);
      } catch (e) {
        console.error(`任务${task.name}执行异常`, e);
      }
    }
  }
}

/**
 * 按 Cron 表达式分组返回任务
 * 用于多账号错开执行（每个任务配自己的 cronExpr）
 * 返回: Map<cronExpr, taskId[]>
 * 注意: 用原生 SQL 避免 drizzle 列名大小写问题
 */
export async function getTaskCronGroups(): Promise<Map<string, number[]>> {
  const globalCron = process.env.GLOBAL_CRON || "0 0 */6 * * *";
  const groups = new Map<string, number[]>();
  try {
    const [rows] = await pool.query(
      "SELECT id, name, enabled, execMode, cronExpr FROM tasks"
    ) as any[];
    for (const task of rows) {
      if (!task.enabled) continue;
      if (task.execMode === 2) continue;  // 仅手动的不参加
      const cron = task.cronExpr || globalCron;
      if (!groups.has(cron)) groups.set(cron, []);
      groups.get(cron)!.push(task.id);
    }
  } catch (e: any) {
    console.error("[getTaskCronGroups] 查询失败，用全局 Cron:", e.message);
    // 查询失败时，用全局 Cron 跑所有启用的任务
    const [rows] = await pool.query(
      "SELECT id FROM tasks WHERE enabled = 1 AND execMode != 2"
    ) as any[];
    groups.set(globalCron, rows.map((r: any) => r.id));
  }
  return groups;
}

export async function getSystemConfig() {
  return {
    free_captcha_enable: 1,
    use_playwright: 1,
    tgBotToken: process.env.TG_BOT_TOKEN ?? "",
    tgChatId: process.env.TG_CHAT_ID ?? ""
  };
}

/**
 * 查询任务执行日志
 * @param taskId 任务ID（可选，不传则查全部）
 * @param limit 返回条数，默认 50
 */
export async function getTaskLogs(taskId?: number, limit = 50) {
  const query = db.select().from(taskLog).orderBy(desc(taskLog.createdAt)).limit(limit);
  if (taskId) {
    return await query.where(eq(taskLog.taskId, taskId));
  }
  return await query;
}
