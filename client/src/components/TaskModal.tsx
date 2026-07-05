import { useEffect, useState } from "react";
import { trpc } from "../lib/trpc";

interface Props {
  close: () => void;
  editId: number | null;
  refresh: () => void;
}

export default function TaskModal({ close, editId, refresh }: Props) {
  const getTask = trpc.task.getOne.useQuery({ id: editId ?? 0 }, { enabled: !!editId });
  const createMut = trpc.task.create.useMutation({
    onSuccess: () => { refresh(); close(); }
  });
  const updateMut = trpc.task.update.useMutation({
    onSuccess: () => { refresh(); close(); }
  });
  const deleteMut = trpc.task.delete.useMutation({
    onSuccess: () => { refresh(); close(); }
  });

  const [form, setForm] = useState({
    name: "",
    url: "",
    username: "",
    password: "",
    renewCycle: 7,
    alertDays: 2,
    taskType: "link",
    customScript: "",
    renewButtonText: "",
    cookies: "",
    renewThresholdMinutes: 0,
    execMode: 1,
    cronExpr: "",
    enabled: true
  });

  useEffect(() => {
    if (getTask.data) setForm(getTask.data);
  }, [getTask.data]);

  const submit = () => {
    if (editId === null) createMut.mutate(form);
    else updateMut.mutate({ id: editId, ...form });
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 w-full max-w-lg rounded-lg p-5 max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold text-white mb-4">
          {editId ? "编辑任务" : "新增任务"}
        </h2>

        <div className="space-y-3">
          <div>
            <label className="text-zinc-300 text-sm">任务名称</label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
              value={form.name}
              onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-zinc-300 text-sm">站点地址</label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
              placeholder="https://example.com/renew?i=xxx"
              value={form.url}
              onChange={e => setForm(p => ({ ...p, url: e.target.value }))}
            />
          </div>

          {/* 任务类型选择器 */}
          <div>
            <label className="text-zinc-300 text-sm">任务类型</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, taskType: "link" }))}
                className={`px-3 py-2 rounded text-sm border ${
                  form.taskType === "link"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-300"
                }`}
              >
                🔗 链接签到
              </button>
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, taskType: "login" }))}
                className={`px-3 py-2 rounded text-sm border ${
                  form.taskType === "login"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-300"
                }`}
              >
                🔐 账号密码登录
              </button>
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, taskType: "cookie" }))}
                className={`px-3 py-2 rounded text-sm border ${
                  form.taskType === "cookie"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-300"
                }`}
              >
                🍪 Cookie 注入
              </button>
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, taskType: "browser" }))}
                className={`px-3 py-2 rounded text-sm border ${
                  form.taskType === "browser"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-300"
                }`}
              >
                🌐 浏览器访问
              </button>
            </div>
            <p className="text-zinc-500 text-xs mt-1">
              {form.taskType === "link" && "🔗 链接签到：仅访问 URL 即完成续期（用 fetch，最快最省资源，适合 host2play/hax 等）"}
              {form.taskType === "login" && "🔐 账号密码登录：Playwright 自动填表 + 提交 + 可选点击按钮（适合普通登录站点）"}
              {form.taskType === "cookie" && "🍪 Cookie 注入：Playwright + Cookie 跳过登录（适合 Discord/Google OAuth 站点）"}
              {form.taskType === "browser" && "🌐 浏览器访问：Playwright 打开页面 + 可选点击按钮（不需要登录的浏览器任务）"}
            </p>
          </div>

          {/* 账号密码 - 只在 login 类型显示 */}
          {(form.taskType === "login") && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-zinc-300 text-sm">账号</label>
                <input
                  className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
                  value={form.username}
                  onChange={e => setForm(p => ({ ...p, username: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-zinc-300 text-sm">密码</label>
                <input
                  className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
                  value={form.password}
                  onChange={e => setForm(p => ({ ...p, password: e.target.value }))}
                />
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-zinc-300 text-sm">
                续期周期(天)
                <span className="text-zinc-500 ml-1">(0=自动同步网站时间)</span>
              </label>
              <input
                type="number"
                min={0}
                className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
                placeholder="0"
                value={form.renewCycle || ""}
                onChange={e => setForm(p => ({ ...p, renewCycle: Number(e.target.value) || 0 }))}
              />
              <p className="text-zinc-500 text-xs mt-1">
                设为 0：下次签到时间由网站剩余时间自动决定<br/>
                设为 N：下次签到时间 = 现在 + N 天
              </p>
            </div>
            <div>
              <label className="text-zinc-300 text-sm">提前提醒天数</label>
              <input
                type="number"
                min={0}
                className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
                placeholder="2"
                value={form.alertDays || ""}
                onChange={e => setForm(p => ({ ...p, alertDays: Number(e.target.value) || 0 }))}
              />
            </div>
          </div>

          {/* 执行模式 */}
          <div>
            <label className="text-zinc-300 text-sm">执行模式</label>
            <div className="grid grid-cols-3 gap-2 mt-1">
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, execMode: 1 }))}
                className={`px-2 py-2 rounded text-xs border ${form.execMode === 1 ? "bg-emerald-600 border-emerald-500 text-white" : "bg-zinc-800 border-zinc-700 text-zinc-300"}`}
              >
                🔄 自动+手动
              </button>
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, execMode: 2 }))}
                className={`px-2 py-2 rounded text-xs border ${form.execMode === 2 ? "bg-emerald-600 border-emerald-500 text-white" : "bg-zinc-800 border-zinc-700 text-zinc-300"}`}
              >
                ✋ 仅手动
              </button>
              <button
                type="button"
                onClick={() => setForm(p => ({ ...p, execMode: 3 }))}
                className={`px-2 py-2 rounded text-xs border ${form.execMode === 3 ? "bg-emerald-600 border-emerald-500 text-white" : "bg-zinc-800 border-zinc-700 text-zinc-300"}`}
              >
                🤖 仅自动
              </button>
            </div>
            <p className="text-zinc-500 text-xs mt-1">
              {form.execMode === 1 && "🔄 Cron 定时自动执行 + 可手动点按钮执行"}
              {form.execMode === 2 && "✋ 不参加 Cron 自动执行，只能手动点'立即签到'"}
              {form.execMode === 3 && "🤖 只参加 Cron 定时执行，面板不显示手动按钮"}
            </p>
          </div>
          <div>
            <label className="text-zinc-300 text-sm">
              续期阈值（分钟）
              <span className="text-zinc-500 ml-1">(可选, 0=总是点击)</span>
            </label>
            <input
              type="number"
              min={0}
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
              placeholder="例如：60"
              value={form.renewThresholdMinutes || 0}
              onChange={e => setForm(p => ({ ...p, renewThresholdMinutes: Number(e.target.value) }))}
            />
            <p className="text-zinc-500 text-xs mt-1">
              自动识别页面剩余/冷却时间。设为 60 表示剩余 60 分钟内才点击续期按钮；
              设为 0 表示不检测时间，总是点击（适合每次执行都强制续期）。
              支持 "90 min"、"02:46 cd"、"21:13:14 remain"、"expires 22:38" 等格式。
            </p>
          </div>
          <div>
            <label className="text-zinc-300 text-sm">
              独立 Cron 表达式
              <span className="text-zinc-500 ml-1">(可选, 留空用全局)</span>
            </label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white font-mono text-sm"
              placeholder="例如：0 1 */6 * * * (每6小时的第1分钟)"
              value={form.cronExpr || ""}
              onChange={e => setForm(p => ({ ...p, cronExpr: e.target.value }))}
            />
            <p className="text-zinc-500 text-xs mt-1">
              多账号错开执行：账号1留空(用全局 0 0 */6)，账号2填 <code className="bg-zinc-800 px-1 rounded">0 1 */6 * * *</code>，
              账号3填 <code className="bg-zinc-800 px-1 rounded">0 2 */6 * * *</code>，避免多个 Playwright 同时跑导致 OOM。
              格式：分 时 日 月 周（6字段，含秒）。
            </p>
          </div>
          <div>
            <label className="text-zinc-300 text-sm">
              续期按钮文字
              <span className="text-zinc-500 ml-1">(可选)</span>
            </label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
              placeholder="例如：+90 min"
              value={form.renewButtonText || ""}
              onChange={e => setForm(p => ({ ...p, renewButtonText: e.target.value }))}
            />
            <p className="text-zinc-500 text-xs mt-1">
              登录成功后，自动点击页面上包含该文字的按钮。留空表示仅完成登录流程。
              常见用法：+90 min、+24h、续期、签到等。
            </p>
          </div>
          <div>
            <label className="text-zinc-300 text-sm">
              登录 Cookie
              <span className="text-zinc-500 ml-1">(可选, OAuth 站点必填)</span>
            </label>
            <textarea
              rows={4}
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white font-mono text-xs"
              placeholder="粘贴 document.cookie 输出，例如：&#10;key1=value1; key2=value2; ..."
              value={form.cookies || ""}
              onChange={e => setForm(p => ({ ...p, cookies: e.target.value }))}
            />
            <p className="text-zinc-500 text-xs mt-1">
              适用于 Discord/Google OAuth 登录的网站。在浏览器已登录状态下，按 F12 → Console，执行
              <code className="bg-zinc-800 px-1 rounded">document.cookie</code>
              ，把输出粘贴到这里。配置后会跳过账号密码登录，直接以 Cookie 状态访问页面。
            </p>
          </div>
          <div>
            <label className="text-zinc-300 text-sm">
              成功关键词 / 自定义脚本
              <span className="text-zinc-500 ml-1">(可选)</span>
            </label>
            <textarea
              rows={4}
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white font-mono text-xs"
              placeholder={"配置成功关键词（推荐，验证是否真签到成功）：\nSUCCESS_KEYWORD:续期成功|renewed|已续期|Renew server\n\n循环点击模式（gaming4free 的 +90min 按钮专用，点击后冷却 4 分钟可重复点击，上限 48 小时）：\nLOOP_MODE:1\nCOOLDOWN_SEC:240\nCAP_HOURS:48\nMAX_CLICKS:35\n\n或自定义 JS 脚本（Playwright 模式登录前执行）"}
              value={form.customScript || ""}
              onChange={e => setForm(p => ({ ...p, customScript: e.target.value }))}
            />
            <p className="text-zinc-500 text-xs mt-1">
              <strong className="text-zinc-400">成功关键词</strong>：以 <code className="bg-zinc-800 px-1 rounded">SUCCESS_KEYWORD:</code> 开头，多个用 <code className="bg-zinc-800 px-1 rounded">|</code> 分隔。
              签到后检查页面是否包含任一关键词，包含才算真成功（不包含则报失败）。
              <br/>
              <strong className="text-zinc-400">示例</strong>：<code className="bg-zinc-800 px-1 rounded">SUCCESS_KEYWORD:续期成功|renewed|Renew server</code>
              <br/>
              <strong className="text-zinc-400">循环点击模式</strong>（gaming4free +90min 按钮）：
              <code className="bg-zinc-800 px-1 rounded block mt-1 whitespace-pre">LOOP_MODE:1
COOLDOWN_SEC:240
CAP_HOURS:48
MAX_CLICKS:35</code>
              <span className="block mt-1">点击 +90min 按钮后等 4 分钟冷却，自动再点，循环直到 48 小时上限。</span>
            </p>
          </div>
          <label className="flex items-center gap-2 text-zinc-300">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={e => setForm(p => ({ ...p, enabled: e.target.checked }))}
            />
            启用该任务
          </label>
        </div>

        <div className="flex justify-between mt-5">
          {editId && (
            <button
              onClick={() => deleteMut.mutate({ id: editId })}
              className="px-3 py-2 bg-red-600 rounded text-white"
            >
              删除
            </button>
          )}
          <div className="flex gap-2 ml-auto">
            <button
              onClick={close}
              className="px-3 py-2 bg-zinc-700 rounded text-white"
            >
              取消
            </button>
            <button
              onClick={submit}
              disabled={createMut.isPending || updateMut.isPending}
              className="px-3 py-2 bg-emerald-600 rounded text-white disabled:opacity-50"
            >
              {createMut.isPending || updateMut.isPending ? "保存中..." : "保存"}
            </button>
          </div>
        </div>

        {/* 显示错误信息（让用户能看到保存失败的原因） */}
        {(createMut.error || updateMut.error || deleteMut.error) && (
          <div className="mt-3 p-3 bg-red-900/50 border border-red-700 rounded text-red-300 text-sm">
            <p className="font-semibold mb-1">操作失败：</p>
            <p className="break-all">
              {createMut.error?.message || updateMut.error?.message || deleteMut.error?.message}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}