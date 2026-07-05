// 前端 tRPC 客户端
// 注意：AppRouter 类型来自后端 server/index.ts，但为了避免 CF Pages 构建
// 时把 server 端的依赖（express / drizzle / mysql2 / playwright / sharp / ddddocr）
// 拉进前端构建链路，这里使用本地类型 stub。
// 本地开发时如需端到端类型安全，可改为：
//   import type { AppRouter } from "../../../server/index";
// 但发布到 Cloudflare Pages 时必须用下面的 stub 形式。
import { createTRPCReact } from "@trpc/react-query";

// 本地类型 stub —— 与 server/index.ts 中 export type AppRouter 结构对齐
// 任何后端路由签名变更需同步更新这里的接口定义
interface AppRouter {
  // 占位：实际路由由后端 _core/trpc.ts 定义
  // 此处只作为类型锚点使用，不影响运行时
  [key: string]: unknown;
}

export const trpc = createTRPCReact<AppRouter>();
