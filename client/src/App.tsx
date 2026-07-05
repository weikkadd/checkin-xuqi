import { useState } from "react";
import { trpc } from "./lib/trpc";
import Home from "./pages/Home";
import Settings from "./components/Settings";
import LogsPage from "./components/LogsPage";
import SystemSettings from "./components/SystemSettings";

const TOKEN_KEY = "checkin_token";
const USERNAME_KEY = "checkin_username";

function getStoredToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function getStoredUsername(): string {
  try { return localStorage.getItem(USERNAME_KEY) || "管理员"; } catch { return "管理员"; }
}

export default function App() {
  const [isLogin, setIsLogin] = useState<boolean>(!!getStoredToken());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [showSysSettings, setShowSysSettings] = useState(false);

  const loginMut = trpc.login.useMutation({
    onSuccess: (data) => {
      try {
        localStorage.setItem(TOKEN_KEY, data.token);
        localStorage.setItem(USERNAME_KEY, username);
      } catch {}
      setIsLogin(true);
    }
  });

  const handleLogout = () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USERNAME_KEY);
    } catch {}
    setIsLogin(false);
  };

  if (!isLogin) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-neutral-950 via-zinc-900 to-neutral-950 flex items-center justify-center p-4">
        <div className="w-full max-w-sm">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-600/20 border border-emerald-500/30 mb-4">
              <span className="text-3xl">🔄</span>
            </div>
            <h1 className="text-2xl font-bold text-white">签到续期任务</h1>
          </div>

          {/* 登录表单 */}
          <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-2xl">
            <div className="space-y-4">
              <div>
                <label className="text-zinc-400 text-xs font-medium mb-1 block">账号</label>
                <input
                  className="w-full bg-zinc-800/80 px-4 py-3 rounded-lg border border-zinc-700 text-white outline-none focus:border-emerald-500 transition-colors"
                  placeholder="请输入账号"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && loginMut.mutate({ username, password })}
                />
              </div>
              <div>
                <label className="text-zinc-400 text-xs font-medium mb-1 block">密码</label>
                <input
                  type="password"
                  className="w-full bg-zinc-800/80 px-4 py-3 rounded-lg border border-zinc-700 text-white outline-none focus:border-emerald-500 transition-colors"
                  placeholder="请输入密码"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && loginMut.mutate({ username, password })}
                />
              </div>
              <button
                className="w-full bg-emerald-600 hover:bg-emerald-500 py-3 rounded-lg font-medium text-white transition-colors disabled:opacity-50"
                onClick={() => loginMut.mutate({ username, password })}
                disabled={loginMut.isPending || !username || !password}
              >
                {loginMut.isPending ? "登录中..." : "🔐 登录"}
              </button>
              {loginMut.error && (
                <p className="text-red-400 text-sm text-center bg-red-900/20 border border-red-800/50 rounded-lg py-2 px-3">
                  {loginMut.error.message}
                </p>
              )}
            </div>
          </div>

          <p className="text-center text-zinc-600 text-xs mt-6">
            签到自动续期管理平台 · Powered by Playwright + tRPC
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* 顶部导航栏 */}
      <nav className="sticky top-0 z-40 bg-zinc-900/80 backdrop-blur-md border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl">🔄</span>
            <span className="text-white font-bold text-lg">签到续期任务</span>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <span className="text-zinc-300 text-sm hidden sm:inline">👋 {getStoredUsername()}</span>
            <button
              onClick={() => setShowLogs(true)}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-300 transition-colors"
            >
              📊 日志
            </button>
            <button
              onClick={() => setShowSysSettings(true)}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-300 transition-colors"
            >
              🔧 系统
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-300 transition-colors"
            >
              ⚙️ 设置
            </button>
            <button
              onClick={handleLogout}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-300 transition-colors"
            >
              退出
            </button>
          </div>
        </div>
      </nav>

      <Home />

      {showSettings && (
        <Settings close={() => setShowSettings(false)} onLogout={handleLogout} />
      )}
      {showLogs && <LogsPage close={() => setShowLogs(false)} />}
      {showSysSettings && <SystemSettings close={() => setShowSysSettings(false)} />}
    </div>
  );
}
