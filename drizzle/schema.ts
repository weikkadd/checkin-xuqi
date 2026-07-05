import { int, text, timestamp, boolean, mysqlTable, varchar } from "drizzle-orm/mysql-core";

// 签到任务主表
export const tasks = mysqlTable("tasks", {
  id: int("id").primaryKey().autoincrement(),
  name: varchar("name", { length: 128 }).notNull(),
  url: text("url").notNull(),
  username: varchar("username", { length: 255 }),
  password: varchar("password", { length: 255 }),
  renewCycle: int("renewCycle").notNull().default(7),
  alertDays: int("alertDays").notNull().default(2),
  // 任务类型:
  // - "link"    链接签到（仅访问 URL，用 fetch，最快最省资源）
  // - "login"   账号密码登录（Playwright 自动填表 + 提交 + 可选点击按钮）
  // - "cookie"  Cookie 注入（Playwright + Cookie，适合 OAuth 站点）
  // - "browser" 浏览器访问（Playwright 打开页面，可选点击按钮，不登录）
  taskType: varchar("taskType", { length: 16 }).notNull().default("link"),
  // 自定义 JS 脚本（登录前执行）
  customScript: text("customScript"),
  // 续期按钮文字 - 登录后自动点击匹配该文字的按钮（如 "+90 min"）
  // 为空表示不自动点击按钮，仅完成登录流程
  renewButtonText: varchar("renewButtonText", { length: 128 }),
  // 登录 Cookie（document.cookie 字符串）
  // 如果配置了 Cookie，会直接注入到浏览器上下文，跳过登录流程
  // 适用于 OAuth 登录的网站（如 Discord/Google 登录的站点）
  cookies: text("cookies"),
  // 执行模式: 1=自动+手动(默认), 2=仅手动, 3=仅自动
  execMode: int("execMode").notNull().default(1),
  // 续期阈值（分钟）- 当页面剩余时间小于此值时才点击续期按钮
  // 例如设为 60：剩余 1 小时内才点 +90 min，否则跳过
  // 0 表示总是点击（不检测时间）
  renewThresholdMinutes: int("renewThresholdMinutes").notNull().default(0),
  // 独立 Cron 表达式（可选）- 为空则用全局 GLOBAL_CRON
  // 多账号错开执行：账号1="0 0 */6 * * *", 账号2="0 1 */6 * * *", 账号3="0 2 */6 * * *"
  // 这样避免多个 Playwright 同时跑导致 OOM
  cronExpr: varchar("cronExpr", { length: 64 }),
  lastRenew: timestamp("lastRenew"),
  nextRenew: timestamp("nextRenew").notNull(),
  enabled: boolean("enabled").notNull().default(true),
  shareLink: text("shareLink"),
  createdAt: timestamp("createdAt").defaultNow(),
  updatedAt: timestamp("updatedAt").onUpdateNow(),
});

// 管理员账号表
export const adminUser = mysqlTable("admin_user", {
  id: int("id").primaryKey().autoincrement(),
  username: varchar("username", { length: 64 }).unique().notNull(),
  password: varchar("password", { length: 128 }).notNull(),
  createdAt: timestamp("createdAt").defaultNow(),
});

// 任务执行日志表
export const taskLog = mysqlTable("task_log", {
  id: int("id").primaryKey().autoincrement(),
  taskId: int("taskId").notNull(),
  taskName: varchar("taskName", { length: 128 }).notNull(),
  success: boolean("success").notNull(),
  errorMsg: text("errorMsg"),
  // 执行耗时(毫秒)
  duration: int("duration"),
  // 签到结果页截图(可选, base64 编码)
  // 注意：默认 TEXT 只有 64KB，base64 JPEG 截图通常 100KB+
  // 部署后需要手动 ALTER TABLE 改成 MEDIUMTEXT（已在 SQL 中说明）
  screenshot: text("screenshot"),
  createdAt: timestamp("createdAt").defaultNow(),
});
