import { useState, useEffect } from "react";
import { trpc } from "../lib/trpc";

interface Props {
  close: () => void;
}

export default function SystemSettings({ close }: Props) {
  const [tgBotToken, setTgBotToken] = useState("");
  const [tgChatId, setTgChatId] = useState("");
  const [globalCron, setGlobalCron] = useState("0 0 */6 * * *");
  const [success, setSuccess] = useState("");

  const configQuery = trpc.system.getConfig.useQuery();

  useEffect(() => {
    if (configQuery.data) {
      setTgBotToken(configQuery.data.tgBotToken || "");
      setTgChatId(configQuery.data.tgChatId || "");
      setGlobalCron(configQuery.data.globalCron || "0 0 */6 * * *");
    }
  }, [configQuery.data]);

  const updateConfigMut = trpc.system.updateConfig.useMutation({
    onSuccess: () => {
      setSuccess("✅ 系统配置已保存");
      setTimeout(() => setSuccess(""), 3000);
    }
  });

  const handleSubmit = () => {
    updateConfigMut.mutate({
      tgBotToken,
      tgChatId,
      globalCron,
    });
  };

  const testTgMut = trpc.system.testTg.useMutation({
    onSuccess: () => {
      setSuccess("✅ TG 测试消息已发送，请检查群");
      setTimeout(() => setSuccess(""), 3000);
    }
  });

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md rounded-xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-xl font-bold text-white">⚙️ 系统设置</h2>
          <button onClick={close} className="text-zinc-400 hover:text-white text-xl">✕</button>
        </div>

        <div className="space-y-4">
          {/* TG Bot Token */}
          <div>
            <label className="text-zinc-300 text-sm">TG Bot Token</label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white font-mono text-xs"
              placeholder="123456:ABC-DEF..."
              value={tgBotToken}
              onChange={e => setTgBotToken(e.target.value)}
            />
            <p className="text-zinc-500 text-xs mt-1">从 @BotFather 获取的 Bot Token</p>
          </div>

          {/* TG Chat ID */}
          <div>
            <label className="text-zinc-300 text-sm">TG Chat ID</label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white font-mono text-xs"
              placeholder="-100xxxxxxx"
              value={tgChatId}
              onChange={e => setTgChatId(e.target.value)}
            />
            <p className="text-zinc-500 text-xs mt-1">TG 群的 Chat ID（带 -100 前缀）</p>
          </div>

          {/* Global Cron */}
          <div>
            <label className="text-zinc-300 text-sm">全局 Cron 表达式</label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white font-mono text-xs"
              placeholder="0 0 */6 * * *"
              value={globalCron}
              onChange={e => setGlobalCron(e.target.value)}
            />
            <p className="text-zinc-500 text-xs mt-1">
              格式：秒 分 时 日 月 周（6字段）。默认每 6 小时执行一次。
            </p>
          </div>

          {/* 测试 TG */}
          <button
            onClick={() => testTgMut.mutate()}
            disabled={testTgMut.isPending || !tgBotToken || !tgChatId}
            className="w-full bg-blue-600 hover:bg-blue-700 py-2.5 rounded-lg text-white font-medium disabled:opacity-50"
          >
            {testTgMut.isPending ? "发送中..." : "🔔 测试 TG 通知"}
          </button>

          {/* 错误信息 */}
          {updateConfigMut.error && (
            <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
              {updateConfigMut.error.message}
            </div>
          )}

          {testTgMut.error && (
            <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
              {testTgMut.error.message}
            </div>
          )}

          {/* 成功信息 */}
          {success && (
            <div className="p-3 bg-emerald-900/30 border border-emerald-700 rounded-lg text-emerald-300 text-sm">
              {success}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={updateConfigMut.isPending}
            className="w-full bg-emerald-600 hover:bg-emerald-700 py-2.5 rounded-lg text-white font-medium disabled:opacity-50"
          >
            {updateConfigMut.isPending ? "保存中..." : "💾 保存配置"}
          </button>
        </div>

        <p className="text-zinc-600 text-xs mt-4 text-center">
          ⚠️ 修改后需要重启后端服务才能生效
        </p>
      </div>
    </div>
  );
}
