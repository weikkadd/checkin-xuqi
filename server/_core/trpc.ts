import { initTRPC, TRPCError } from "@trpc/server";
import { z } from "zod";
import superjson from "superjson";
import type { Request, Response } from "express";
import {
  getAllTasks,
  getTaskById,
  createTask,
  updateTask,
  deleteTask,
  runSingleTask,
  testTaskAlert,
  verifyAdmin,
  getSystemConfig,
  getTaskLogs,
} from "../db";

export function createContext({ req, res }: { req: Request; res: Response }) {
  return { req, res };
}
type Context = ReturnType<typeof createContext>;

// 启用 superjson transformer，让 tRPC v10 server 兼容 @trpc/client v10
// 默认的请求格式 {"0":{"json":{...}}} 和响应 {"result":{"data":{"json":...}}}
// 如果不启用 transformer，前端发的 json 字段会被忽略，导致 input 验证失败
const t = initTRPC.context<Context>().create({
  transformer: superjson,
});
const publicProcedure = t.procedure;

const authProcedure = t.procedure.use(async ({ ctx, next }) => {
  const authHeader = ctx.req.headers.authorization;
  if (!authHeader) throw new TRPCError({ code: "UNAUTHORIZED", message: "未登录" });
  return next({ ctx });
});

export const appRouter = t.router({
  login: publicProcedure
    .input(z.object({ username: z.string(), password: z.string() }))
    .mutation(async ({ input }) => {
      const ok = await verifyAdmin(input.username, input.password);
      if (!ok) throw new TRPCError({ code: "UNAUTHORIZED", message: "账号密码错误" });
      return { token: "simple-token-ok" };
    }),

  auth: t.router({
    // 获取当前用户信息
    getProfile: authProcedure.query(async ({ ctx }) => {
      // 从 admin_user 表获取
      const { db } = await import("../db");
      const { adminUser } = await import("../../drizzle/schema");
      const { eq } = await import("drizzle-orm");
      const res = await db.select().from(adminUser).limit(1);
      if (res.length === 0) throw new TRPCError({ code: "NOT_FOUND", message: "用户不存在" });
      return { id: res[0].id, username: res[0].username };
    }),

    // 修改用户名和密码
    updateProfile: authProcedure
      .input(z.object({
        currentPassword: z.string(),
        newUsername: z.string().optional(),
        newPassword: z.string().optional(),
      }))
      .mutation(async ({ input }) => {
        const { db } = await import("../db");
        const { adminUser } = await import("../../drizzle/schema");
        const { eq } = await import("drizzle-orm");

        // 获取当前用户
        const res = await db.select().from(adminUser).limit(1);
        if (res.length === 0) throw new TRPCError({ code: "NOT_FOUND", message: "用户不存在" });

        // 验证当前密码
        if (res[0].password !== input.currentPassword) {
          throw new TRPCError({ code: "UNAUTHORIZED", message: "当前密码错误" });
        }

        // 更新
        const updateData: any = {};
        if (input.newUsername && input.newUsername.trim()) {
          updateData.username = input.newUsername.trim();
        }
        if (input.newPassword && input.newPassword.trim()) {
          updateData.password = input.newPassword.trim();
        }

        if (Object.keys(updateData).length === 0) {
          throw new TRPCError({ code: "BAD_REQUEST", message: "没有要更新的内容" });
        }

        await db.update(adminUser).set(updateData).where(eq(adminUser.id, res[0].id));
        return { success: true, username: updateData.username || res[0].username };
      }),
  }),

  task: t.router({
    getAll: publicProcedure.query(async () => await getAllTasks()),
    getOne: publicProcedure.input(z.object({ id: z.number() })).query(async ({ input }) => await getTaskById(input.id)),
    create: authProcedure.input(z.object({
      name: z.string(),
      url: z.string(),
      username: z.string().optional(),
      password: z.string().optional(),
      renewCycle: z.number().min(0),
      alertDays: z.number().min(0),
      taskType: z.string().optional(),
      customScript: z.string().optional(),
      renewButtonText: z.string().optional(),
      cookies: z.string().optional(),
      renewThresholdMinutes: z.number().min(0).default(0),
      execMode: z.number().min(1).max(3).default(1),
      enabled: z.boolean()
    })).mutation(async ({ input }) => await createTask(input)),

    update: authProcedure.input(z.object({
      id: z.number(),
      name: z.string().optional(),
      url: z.string().optional(),
      username: z.string().optional(),
      password: z.string().optional(),
      renewCycle: z.number().min(0).optional(),
      alertDays: z.number().min(0).optional(),
      taskType: z.string().optional(),
      customScript: z.string().optional(),
      renewButtonText: z.string().optional(),
      cookies: z.string().optional(),
      renewThresholdMinutes: z.number().min(0).optional(),
      execMode: z.number().min(1).max(3).optional(),
      cronExpr: z.string().optional(),
      enabled: z.boolean().optional(),
      shareLink: z.string().optional()
    })).mutation(async ({ input }) => {
      const { id, ...rest } = input;
      await updateTask(id, rest);
      return true;
    }),

    delete: authProcedure.input(z.object({ id: z.number() })).mutation(async ({ input }) => {
      await deleteTask(input.id);
      return true;
    }),

    runNow: authProcedure.input(z.object({ taskId: z.number() })).mutation(async ({ input }) => {
      return await runSingleTask(input.taskId);
    }),

    // 手动标记签到成功（用户在浏览器手动完成签到后调用）
    markSuccess: authProcedure.input(z.object({ taskId: z.number() })).mutation(async ({ input }) => {
      const { markManualSuccess } = await import("../db");
      return await markManualSuccess(input.taskId);
    }),

    testAlert: authProcedure.input(z.object({ taskId: z.number() })).mutation(async ({ input }) => {
      await testTaskAlert(input.taskId);
      return true;
    }),

    getLogs: publicProcedure
      .input(z.object({
        taskId: z.number().optional(),
        limit: z.number().min(1).max(200).default(50),
      }))
      .query(async ({ input }) => await getTaskLogs(input.taskId, input.limit)),
  }),

  system: t.router({
    getConfig: publicProcedure.query(async () => await getSystemConfig())
  })
});

export type AppRouter = typeof appRouter;
