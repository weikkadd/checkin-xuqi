import { useState } from "react";
import { trpc } from "../lib/trpc";

interface Props {
  close: () => void;
}

export default function LogsPage({ close }: Props) {
  const [taskId, setTaskId] = useState<number | undefined>(undefined);
  const [limit, setLimit] = useState(50);
  const [showScreenshot, setShowScreenshot] = useState<string | null>(null);

  const logsQuery = trpc.task.getLogs.useQuery({
    taskId: taskId || undefined,
    limit,
  });

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-zinc-700 w-full max-w-4xl rounded-xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-5 sticky top-0 bg-zinc-900 pb-3 border-b border-zinc-800">
          <h2 className="text-xl font-bold text-white">📊 任务日志</h2>
          <button onClick={close} className="text-zinc-400 hover:text-white text-xl">✕</button>
        </div>

        {/* 筛选 */}
        <div className="flex gap-3 mb-4">
          <div>
            <label className="text-zinc-400 text-xs block mb-1">任务 ID</label>
            <input
              type="number"
              className="w-32 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
              placeholder="全部"
              value={taskId || ""}
              onChange={e => setTaskId(e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
          <div>
            <label className="text-zinc-400 text-xs block mb-1">条数</label>
            <select
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
              value={limit}
              onChange={e => setLimit(Number(e.target.value))}
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>

        {/* 日志列表 */}
        {logsQuery.isLoading ? (
          <p className="text-zinc-400 text-center py-8">加载中...</p>
        ) : logsQuery.data && logsQuery.data.length > 0 ? (
          <div className="space-y-2">
            {logsQuery.data.map((log: any) => (
              <div
                key={log.id}
                className={`p-3 rounded-lg border ${
                  log.success
                    ? "bg-emerald-900/20 border-emerald-700/30"
                    : "bg-red-900/20 border-red-700/30"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      log.success ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
                    }`}>
                      {log.success ? "✅ 成功" : "❌ 失败"}
                    </span>
                    <span className="text-white text-sm font-medium">{log.taskName}</span>
                    <span className="text-zinc-500 text-xs">ID: {log.taskId}</span>
                  </div>
                  <span className="text-zinc-500 text-xs">
                    {new Date(log.createdAt).toLocaleString("zh-CN")}
                  </span>
                </div>
                {log.errorMsg && (
                  <p className="text-zinc-400 text-xs mt-1 break-all">{log.errorMsg}</p>
                )}
                <div className="flex items-center gap-3 mt-1">
                  {log.duration != null && log.duration > 0 && (
                    <span className="text-zinc-500 text-xs">耗时: {log.duration}ms</span>
                  )}
                  {log.screenshot && (
                    <button
                      onClick={() => setShowScreenshot(log.screenshot)}
                      className="text-blue-400 text-xs hover:underline"
                    >
                      📸 查看截图
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-zinc-400 text-center py-8">暂无日志</p>
        )}
      </div>

      {/* 截图弹窗 */}
      {showScreenshot && (
        <div
          className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4"
          onClick={() => setShowScreenshot(null)}
        >
          <img
            src={`data:image/jpeg;base64,${showScreenshot}`}
            alt="截图"
            className="max-w-full max-h-full rounded-lg"
          />
        </div>
      )}
    </div>
  );
}
