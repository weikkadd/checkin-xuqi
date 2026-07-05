import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { httpBatchLink } from "@trpc/client";
import superjson from "superjson";
import { trpc } from "./lib/trpc";
import App from "./App";

const queryClient = new QueryClient();

// 后端 tRPC 端点
// 优先读 CF Pages 环境变量 VITE_API_URL；如果没有（用户没配），用写死的 fallback
// 注意：fallback 现在指向 HuggingFace Spaces（16GB 内存，能跑 Playwright）
// 之前指向 Render（512MB 内存，跑 Chromium 会 OOM）
const API_URL =
  import.meta.env.VITE_API_URL ||
  "https://checkin-api-kkd11.zocomputer.io/trpc";

// 注意：@trpc/react-query v10 的 createClient 需要 { links: [...] } 配置
// 而不是直接传 { url: '...' }，否则会报错：
//   "Cannot read properties of undefined (reading 'map')"
// 因为内部构造函数会访问 options.links.map(...)
//
// transformer: superjson 必须与后端 _core/trpc.ts 的 transformer 配置保持一致
// 否则前端发 {0:{json:{...}}} 后端读不到，后端返回 {result:{data:{json:...}}} 前端也读不到
//
// 注意：不要使用 credentials: "include"
// 因为后端 CORS 配的是 Access-Control-Allow-Origin: *（通配符），
// 浏览器规定通配符 + credentials 不能同时使用，会报 "Failed to fetch"
// 这个项目用 token 鉴权（localStorage），不需要 cookie，所以用默认的 same-origin 即可
//
// headers() 函数：每次请求都会调用，从 localStorage 读取 token 加到 Authorization 头
// 后端的 authProcedure 会检查这个头，没有就返回 UNAUTHORIZED
const trpcClient = trpc.createClient({
  transformer: superjson,
  links: [
    httpBatchLink({
      url: API_URL,
      headers() {
        const token = localStorage.getItem("checkin_token");
        return token ? { Authorization: `Bearer ${token}` } : {};
      },
    }),
  ],
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <trpc.Provider client={trpcClient} queryClient={queryClient}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </trpc.Provider>
  </React.StrictMode>
);
