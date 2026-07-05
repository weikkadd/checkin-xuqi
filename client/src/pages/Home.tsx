import { useState, useEffect } from "react";
import { trpc } from "../lib/trpc";
import TaskModal from "../components/TaskModal";
import LogsPage from "../components/LogsPage";
import SystemSettings from "../components/SystemSettings";

// 计算任务状态
function getTaskStatus(nextRenew: string, alertDays: number) {
  const now = new Date();
  const next = new Date(nextRenew);
  const diffMs = next.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  if (diffMs < 0) {
    return { text: `已过期 ${Math.abs(diffDays)} 天`, color: "bg-red-500/20 text-red-300 border-red-500/40", status: "expired" as const };
  }
  if (diffDays <= alertDays) {
    return { text: `还有 ${diffDays} 天`, color: "bg-amber-500/20 text-amber-300 border-amber-500/40", status: "warning" as const };
  }
  return { text: `还有 ${diffDays} 天`, color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40", status: "normal" as const };
}

function formatTime(t: string | null | undefined) {
  if (!t) return "—";
  const d = new Date(t);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

  if (Math.abs(diffDays) >= 1) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} (${diffDays > 0 ? diffDays + "天后" : Math.abs(diffDays) + "天前"})`;
  }
  if (Math.abs(diffHours) >= 1) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} (${diffHours > 0 ? diffHours + "小时后" : Math.abs(diffHours) + "小时前"})`;
  }
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} (刚刚)`;
}

export default function Home() {
  const [openModal, setOpenModal] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [showBgModal, setShowBgModal] = useState(false);
  const [bgUrl, setBgUrl] = useState("");
  const [bgInput, setBgInput] = useState("");
  const [runningTaskId, setRunningTaskId] = useState<number | null>(null);
  const [runResult, setRunResult] = useState<{ [key: number]: string }>({});
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [showSysSettings, setShowSysSettings] = useState(false);

  const taskQuery = trpc.task.getAll.useQuery();
  const runTaskMut = trpc.task.runNow.useMutation();
  const testNotifyMut = trpc.task.testAlert.useMutation();
  const deleteMut = trpc.task.delete.useMutation();
  const markSuccessMut = trpc.task.markSuccess.useMutation();

  useEffect(() => {
    const saved = localStorage.getItem("panel_bg_url") || "";
    setBgUrl(saved);
    setBgInput(saved);
  }, []);

  const openAdd = () => { setEditId(null); setOpenModal(true); };
  const openEdit = (id: number) => { setEditId(id); setOpenModal(true); };

  const handleRun = (taskId: number) => {
    setRunningTaskId(taskId);
    runTaskMut.mutate({ taskId }, {
      onSuccess: (data) => {
        const msg = data.success ? `✅ ${data.msg}` : `❌ ${data.msg}`;
        setRunResult(prev => ({ ...prev, [taskId]: msg }));
        setRunningTaskId(null);
        taskQuery.refetch();
        setTimeout(() => {
          setRunResult(prev => { const n = { ...prev }; delete n[taskId]; return n; });
        }, 8000);
      },
      onError: (err) => {
        setRunResult(prev => ({ ...prev, [taskId]: `❌ ${err.message}` }));
        setRunningTaskId(null);
      }
    });
  };

  const handleDelete = (taskId: number, taskName: string) => {
    if (!confirm(`确定删除任务「${taskName}」吗？`)) return;
    deleteMut.mutate({ id: taskId }, {
      onSuccess: () => taskQuery.refetch()
    });
  };

  const copyShareLink = (taskId: number, link: string) => {
    navigator.clipboard.writeText(link).then(() => {
      setCopiedId(taskId);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const saveBg = () => {
    localStorage.setItem("panel_bg_url", bgInput);
    setBgUrl(bgInput);
    setShowBgModal(false);
  };

  const clearBg = () => {
    localStorage.removeItem("panel_bg_url");
    setBgUrl(""); setBgInput(""); setShowBgModal(false);
  };

  if (taskQuery.isLoading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-white text-lg">加载中...</div>
    </div>
  );
  if (taskQuery.isError) return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="text-red-300 bg-red-900/30 border border-red-700 rounded-lg p-4">
        加载失败：{taskQuery.error.message}
      </div>
    </div>
  );

  const tasks = taskQuery.data || [];

  // 统计
  const stats = {
    total: tasks.length,
    expired: tasks.filter(t => new Date(t.nextRenew) < new Date()).length,
    warning: tasks.filter(t => {
      const diff = Math.ceil((new Date(t.nextRenew).getTime() - Date.now()) / 86400000);
      return diff >= 0 && diff <= t.alertDays;
    }).length,
    normal: tasks.filter(t => {
      const diff = Math.ceil((new Date(t.nextRenew).getTime() - Date.now()) / 86400000);
      return diff > t.alertDays;
    }).length,
  };

  const bgStyle: React.CSSProperties = bgUrl ? {
    backgroundImage: `url(${bgUrl})`,
    backgroundSize: "cover",
    backgroundPosition: "center",
    backgroundAttachment: "fixed",
  } : {};

  return (
    <div className="min-h-screen" style={bgStyle}>
      <div className={bgUrl ? "min-h-screen bg-black/50 backdrop-blur-sm" : ""}>
        <div className="max-w-7xl mx-auto px-4 py-6">
          {/* 标题区 */}
          <div className="flex justify-between items-center mb-2">
            <div>
              <h1 className="text-2xl font-bold text-white">我的签到任务</h1>
              <p className="text-zinc-400 text-sm mt-1">追踪每个服务的签到周期，避免因过期导致服务中断。</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowBgModal(true)} className="bg-purple-600/80 hover:bg-purple-700 px-4 py-2 rounded-lg text-white text-sm backdrop-blur-sm">🎨 背景</button>
              <button onClick={openAdd} className="bg-emerald-600 hover:bg-emerald-700 px-4 py-2 rounded-lg text-white">+ 新建任务</button>
            </div>
          </div>

          {/* 统计卡片 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-6">
            <div className="bg-zinc-900/80 backdrop-blur-md rounded-xl p-4 border border-zinc-800">
              <div className="text-zinc-400 text-xs font-medium">任务总数</div>
              <div className="text-3xl font-bold text-white mt-1">{stats.total}</div>
            </div>
            <div className="bg-zinc-900/80 backdrop-blur-md rounded-xl p-4 border border-red-900/50">
              <div className="text-zinc-400 text-xs font-medium">已过期</div>
              <div className="text-3xl font-bold text-red-400 mt-1">{stats.expired}</div>
            </div>
            <div className="bg-zinc-900/80 backdrop-blur-md rounded-xl p-4 border border-amber-900/50">
              <div className="text-zinc-400 text-xs font-medium">即将到期</div>
              <div className="text-3xl font-bold text-amber-400 mt-1">{stats.warning}</div>
            </div>
            <div className="bg-zinc-900/80 backdrop-blur-md rounded-xl p-4 border border-emerald-900/50">
              <div className="text-zinc-400 text-xs font-medium">正常</div>
              <div className="text-3xl font-bold text-emerald-400 mt-1">{stats.normal}</div>
            </div>
          </div>

          {/* 任务列表 */}
          {tasks.length === 0 ? (
            <div className="text-center py-20">
              <div className="text-zinc-400 text-lg mb-4">还没有任务</div>
              <button onClick={openAdd} className="bg-emerald-600 hover:bg-emerald-700 px-6 py-3 rounded-lg text-white">+ 创建第一个任务</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {tasks.map(item => {
                const badge = getTaskStatus(item.nextRenew, item.alertDays);
                const isRunning = runningTaskId === item.id;
                const result = runResult[item.id];
                return (
                  <div key={item.id} className="bg-zinc-900/80 backdrop-blur-md rounded-xl p-5 border border-zinc-800 hover:border-zinc-700 transition-colors shadow-xl">
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-lg font-semibold text-white">{item.name}</h3>
                      <span className={`text-xs px-2 py-1 rounded border ${badge.color} whitespace-nowrap`}>{badge.text}</span>
                    </div>
                    <p className="text-zinc-500 text-xs truncate mb-3 font-mono">{item.url}</p>
                    <div className="space-y-1 text-sm text-zinc-300 mb-3 bg-black/30 rounded-lg p-3">
                      <div className="flex justify-between"><span className="text-zinc-500">签到间隔</span><span>{item.renewCycle} 天</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">上次签到</span><span>{formatTime(item.lastRenew)}</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">下次签到</span><span className="text-emerald-300">{formatTime(item.nextRenew)}</span></div>
                    </div>
                    <div className="text-xs text-zinc-400 mb-3 flex items-center gap-2">
                      <span>⏰ 提前 {item.alertDays} 天</span>
                      <span className="text-zinc-600">|</span>
                      <span>{item.enabled ? "✅ 已启用" : "❌ 已停用"}</span>
                      <span className="text-zinc-600">|</span>
                      <span className="text-zinc-500">{item.taskType || "link"}</span>
                    </div>
                    {item.shareLink && (
                      <div className="text-xs text-zinc-500 mb-3 flex items-center gap-2">
                        <span className="truncate flex-1">🔗 {item.shareLink.substring(0, 40)}...</span>
                        <button onClick={() => copyShareLink(item.id, item.shareLink!)} className="text-emerald-400 hover:text-emerald-300">
                          {copiedId === item.id ? "✅ 已复制" : "📋 复制"}
                        </button>
                      </div>
                    )}
                    {result === "__MANUAL_PENDING__" && (
                      <div className="mb-3 p-2 bg-blue-900/30 border border-blue-700 rounded-lg text-xs">
                        <p className="text-blue-300 mb-2">签到页面已打开，完成签到后点击：</p>
                        <button
                          onClick={() => {
                            markSuccessMut.mutate({ taskId: item.id }, {
                              onSuccess: () => {
                                setRunResult(prev => ({ ...prev, [item.id]: "✅ 手动签到已标记成功，TG 通知已发送" }));
                                taskQuery.refetch();
                                setTimeout(() => {
                                  setRunResult(prev => { const n = { ...prev }; delete n[item.id]; return n; });
                                }, 8000);
                              }
                            });
                          }}
                          disabled={markSuccessMut.isPending}
                          className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white text-xs disabled:opacity-50"
                        >
                          {markSuccessMut.isPending ? "⏳ 处理中..." : "✅ 确认签到成功"}
                        </button>
                        <button
                          onClick={() => {
                            setRunResult(prev => { const n = { ...prev }; delete n[item.id]; return n; });
                          }}
                          className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-white text-xs ml-2"
                        >
                          取消
                        </button>
                      </div>
                    )}
                    {result && result !== "__MANUAL_PENDING__" && (
                      <div className="mb-3 p-2 bg-black/50 rounded-lg text-xs text-zinc-200 border border-zinc-700 max-h-32 overflow-y-auto break-all">{result}</div>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => handleRun(item.id)} disabled={isRunning}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white text-xs disabled:opacity-50">
                        {isRunning ? "⏳ 执行中..." : "🔄 自动续期"}
                      </button>
                      <button onClick={() => {
                        // 打开签到页面
                        window.open(item.url, '_blank');
                        // 在卡片上显示"确认成功"按钮
                        setRunResult(prev => ({ ...prev, [item.id]: "__MANUAL_PENDING__" }));
                      }}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-xs">
                        ✋ 手动签到
                      </button>
                      <button onClick={() => testNotifyMut.mutate({ taskId: item.id })} disabled={testNotifyMut.isPending}
                        className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 rounded-lg text-white text-xs disabled:opacity-50">🔔 测试</button>
                      <button onClick={() => openEdit(item.id)}
                        className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-white text-xs">✏️ 编辑</button>
                      <button onClick={() => handleDelete(item.id, item.name)}
                        className="px-3 py-1.5 bg-red-600/80 hover:bg-red-700 rounded-lg text-white text-xs">🗑 删除</button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {openModal && <TaskModal close={() => setOpenModal(false)} editId={editId} refresh={() => taskQuery.refetch()} />}

          {/* 背景图设置弹窗 */}
          {showBgModal && (
            <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
              <div className="bg-zinc-900 border border-zinc-700 w-full max-w-lg rounded-xl p-5 max-h-[90vh] overflow-y-auto">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-bold text-white">🎨 设置背景图</h2>
                  <button onClick={() => setShowBgModal(false)} className="text-zinc-400 hover:text-white text-xl">✕</button>
                </div>

                {/* 预设源 */}
                <div className="mb-4">
                  <p className="text-zinc-300 text-sm mb-2 font-medium">📚 预设背景源（点击应用）</p>
                  <div className="grid grid-cols-2 gap-2">
                    <button onClick={() => setBgInput("https://picsum.photos/1920/1080")}
                      className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg p-2 text-left text-xs text-zinc-300">
                      🏔️ 随机风景<div className="text-zinc-500 text-[10px]">picsum.photos</div>
                    </button>
                    <button onClick={() => setBgInput("https://picsum.photos/seed/anime/1920/1080")}
                      className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg p-2 text-left text-xs text-zinc-300">
                      🎮 随机图片<div className="text-zinc-500 text-[10px]">picsum/seed</div>
                    </button>
                    <button onClick={() => setBgInput("https://bing.img.run/1920x1080.php")}
                      className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg p-2 text-left text-xs text-zinc-300">
                      🌅 Bing 每日<div className="text-zinc-500 text-[10px]">bing.img.run</div>
                    </button>
                    <button onClick={() => setBgInput("https://api.dujin.org/img.php")}
                      className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg p-2 text-left text-xs text-zinc-300">
                      🌈 随机二次元<div className="text-zinc-500 text-[10px]">dujin.org</div>
                    </button>
                  </div>
                </div>

                {/* 自定义 URL */}
                <div className="mb-4">
                  <p className="text-zinc-300 text-sm mb-2 font-medium">🔗 自定义图片 URL</p>
                  <input type="text" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
                    placeholder="https://example.com/bg.jpg" value={bgInput} onChange={e => setBgInput(e.target.value)} />
                </div>

                {/* 本地上传 */}
                <div className="mb-4">
                  <p className="text-zinc-300 text-sm mb-2 font-medium">📤 上传本地图片</p>
                  <input type="file" accept="image/*" onChange={e => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    if (file.size > 2 * 1024 * 1024) { alert("图片超过 2MB"); return; }
                    const reader = new FileReader();
                    reader.onload = () => setBgInput(reader.result as string);
                    reader.readAsDataURL(file);
                  }} className="block w-full text-sm text-zinc-300 file:mr-3 file:py-1 file:px-3 file:rounded-lg file:border-0 file:bg-emerald-600 file:text-white file:text-xs file:hover:bg-emerald-700" />
                </div>

                {/* 预览 */}
                {bgInput && (
                  <div className="mb-4">
                    <p className="text-zinc-300 text-sm mb-2 font-medium">👁️ 预览</p>
                    <div className="aspect-video bg-zinc-800 rounded-lg overflow-hidden border border-zinc-700">
                      <img src={bgInput} alt="preview" className="w-full h-full object-cover"
                        onError={() => alert("图片加载失败！请换一个 URL。")} />
                    </div>
                  </div>
                )}

                <div className="flex justify-between">
                  <button onClick={clearBg} className="px-4 py-2 bg-red-600/80 hover:bg-red-700 rounded-lg text-white text-sm">清除背景</button>
                  <div className="flex gap-2">
                    <button onClick={() => setShowBgModal(false)} className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-white text-sm">取消</button>
                    <button onClick={saveBg} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white text-sm">保存</button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {showLogs && <LogsPage close={() => setShowLogs(false)} />}
      {showSysSettings && <SystemSettings close={() => setShowSysSettings(false)} />}
    </div>
  );
}
