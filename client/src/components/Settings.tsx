import { useState } from "react";
import { trpc } from "../lib/trpc";

interface Props {
  close: () => void;
  onLogout: () => void;
}

export default function Settings({ close, onLogout }: Props) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [success, setSuccess] = useState("");

  const profileQuery = trpc.auth.getProfile.useQuery();
  const updateMut = trpc.auth.updateProfile.useMutation({
    onSuccess: (data) => {
      setSuccess(`✅ 修改成功！新用户名：${data.username}`);
      // 更新 localStorage 里的用户名
      try { localStorage.setItem("checkin_username", data.username); } catch {}
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      // 3 秒后关闭
      setTimeout(() => close(), 3000);
    }
  });

  const handleSubmit = () => {
    if (!currentPassword) { alert("请输入当前密码"); return; }
    if (newPassword && newPassword !== confirmPassword) { alert("两次密码不一致"); return; }
    if (!newUsername && !newPassword) { alert("请至少填写一个要修改的字段"); return; }

    updateMut.mutate({
      currentPassword,
      newUsername: newUsername || undefined,
      newPassword: newPassword || undefined,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md rounded-xl p-6">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-xl font-bold text-white">⚙️ 个人设置</h2>
          <button onClick={close} className="text-zinc-400 hover:text-white text-xl">✕</button>
        </div>

        {/* 当前信息 */}
        <div className="bg-zinc-800/50 rounded-lg p-3 mb-4">
          <p className="text-zinc-400 text-xs">当前用户名</p>
          <p className="text-white font-medium">{profileQuery.data?.username || "加载中..."}</p>
        </div>

        <div className="space-y-4">
          {/* 当前密码 */}
          <div>
            <label className="text-zinc-300 text-sm">当前密码 *</label>
            <input
              type="password"
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white"
              placeholder="请输入当前密码"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
            />
          </div>

          {/* 新用户名 */}
          <div>
            <label className="text-zinc-300 text-sm">新用户名（不修改则留空）</label>
            <input
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white"
              placeholder={profileQuery.data?.username || "新用户名"}
              value={newUsername}
              onChange={e => setNewUsername(e.target.value)}
            />
          </div>

          {/* 新密码 */}
          <div>
            <label className="text-zinc-300 text-sm">新密码（不修改则留空）</label>
            <input
              type="password"
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white"
              placeholder="新密码"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
            />
          </div>

          {/* 确认新密码 */}
          <div>
            <label className="text-zinc-300 text-sm">确认新密码</label>
            <input
              type="password"
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white"
              placeholder="再次输入新密码"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
            />
          </div>

          {/* 错误信息 */}
          {updateMut.error && (
            <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
              {updateMut.error.message}
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
            disabled={updateMut.isPending}
            className="w-full bg-emerald-600 hover:bg-emerald-700 py-2.5 rounded-lg text-white font-medium disabled:opacity-50"
          >
            {updateMut.isPending ? "保存中..." : "💾 保存修改"}
          </button>
        </div>

        <p className="text-zinc-600 text-xs mt-4 text-center">
          修改密码后需要重新登录
        </p>
      </div>
    </div>
  );
}
