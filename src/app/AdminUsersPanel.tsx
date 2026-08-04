"use client";

import React, { useState, useEffect } from "react";

interface UserItem {
  id: number;
  username: string;
  email: string | null;
  name: string | null;
  role: string;
  scope_value: string | null;
  employee_code: string | null;
  scope_channel: string | null;
  status: string;
  is_active: number;
  created_at: string;
}

interface AdminUsersPanelProps {
  authToken: string;
  onClose: () => void;
}

export default function AdminUsersPanel({ authToken, onClose }: AdminUsersPanelProps) {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<UserItem | null>(null);
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);

  // Form phê duyệt state
  const [role, setRole] = useState<string>("qlv");
  const [scopeValue, setScopeValue] = useState<string>("MB");
  const [employeeCode, setEmployeeCode] = useState<string>("");
  const [scopeChannel, setScopeChannel] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  // Form tạo tài khoản mới state
  const [newUsername, setNewUsername] = useState<string>("");
  const [newPassword, setNewPassword] = useState<string>("");
  const [newEmail, setNewEmail] = useState<string>("");
  const [newName, setNewName] = useState<string>("");
  const [newRole, setNewRole] = useState<string>("qlv");
  const [newScopeValue, setNewScopeValue] = useState<string>("");
  const [newEmployeeCode, setNewEmployeeCode] = useState<string>("");
  const [newScopeChannel, setNewScopeChannel] = useState<string>("");
  const [createMsg, setCreateMsg] = useState<{ text: string; type: "success" | "error"; pwd?: string } | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const url = filterStatus ? `/api/admin/users?status=${filterStatus}` : "/api/admin/users";
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Không thể tải danh sách tài khoản");
      setUsers(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [filterStatus]);

  const handleApprove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    setActionLoading(true);
    try {
      const res = await fetch(`/api/admin/users/${encodeURIComponent(selectedUser.username)}/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          role,
          scope_value: (role === "c_level" || role === "admin_ops") ? null : (scopeValue || null),
          employee_code: role === "qlv" ? (employeeCode.trim() || null) : null,
          scope_channel: (role === "c_level" || role === "admin_ops") ? null : (scopeChannel || null),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Phê duyệt thất bại");

      setSelectedUser(null);
      fetchUsers();
    } catch (err: any) {
      alert("Lỗi: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateUserSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading(true);
    setCreateMsg(null);

    try {
      const res = await fetch("/api/admin/users/create", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword.trim() || null,
          email: newEmail.trim() || null,
          name: newName.trim() || null,
          role: newRole,
          scope_value: newRole === "c_level" ? null : (newScopeValue || null),
          employee_code: newRole === "qlv" ? (newEmployeeCode.trim() || null) : null,
          scope_channel: newScopeChannel || null,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Tạo tài khoản thất bại");

      setCreateMsg({
        text: data.message || "Tạo tài khoản thành công!",
        type: "success",
        pwd: data.generated_password,
      });

      // Reset form
      setNewUsername("");
      setNewPassword("");
      setNewEmail("");
      setNewName("");
      setNewEmployeeCode("");
      setNewScopeValue("");
      setNewScopeChannel("");
      fetchUsers();
    } catch (err: any) {
      setCreateMsg({ text: err.message, type: "error" });
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleActive = async (username: string) => {
    try {
      const res = await fetch(`/api/admin/users/${encodeURIComponent(username)}/toggle-active`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Thao tác thất bại");
      fetchUsers();
    } catch (err: any) {
      alert("Lỗi: " + err.message);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl border border-slate-200 overflow-hidden my-8">
        {/* Header */}
        <div className="bg-slate-900 text-white p-5 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold">🛡️ Quản lý & Phê duyệt Tài khoản Nhân viên</h2>
            <p className="text-xs text-slate-400">Dành riêng cho Quản trị viên C-Level / Ban Điều Hành</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => { setShowCreateModal(true); setCreateMsg(null); }}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold text-xs shadow-md transition flex items-center gap-1.5"
            >
              ➕ Tạo Tài khoản Mới
            </button>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center font-bold text-sm transition"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="bg-slate-50 border-b border-slate-200 p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-600">Lọc trạng thái:</span>
            <button
              onClick={() => setFilterStatus("")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                filterStatus === ""
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              📋 Tất cả tài khoản
            </button>
            <button
              onClick={() => setFilterStatus("pending")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                filterStatus === "pending"
                  ? "bg-amber-600 text-white shadow-sm"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              ⏳ Chờ duyệt (Pending)
            </button>
            <button
              onClick={() => setFilterStatus("approved")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                filterStatus === "approved"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              ✅ Đã duyệt (Approved)
            </button>
          </div>

          <button
            onClick={fetchUsers}
            className="text-xs font-semibold text-blue-700 hover:text-blue-900 bg-blue-50 px-3 py-1.5 rounded-lg border border-blue-200"
          >
            🔄 Tải lại
          </button>
        </div>

        {/* Content Table */}
        <div className="p-5 max-h-[60vh] overflow-y-auto">
          {error && <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg mb-4">{error}</div>}

          {loading ? (
            <div className="py-12 text-center text-slate-500 text-sm">Đang tải danh sách tài khoản...</div>
          ) : users.length === 0 ? (
            <div className="py-12 text-center text-slate-400 text-sm">Không có tài khoản nào phù hợp với bộ lọc.</div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50">
                  <th className="p-3">Tài khoản / Email</th>
                  <th className="p-3">Họ tên</th>
                  <th className="p-3">Trạng thái</th>
                  <th className="p-3">Vai trò & Phạm vi</th>
                  <th className="p-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50/80 transition">
                    <td className="p-3">
                      <div className="font-semibold text-slate-900">{u.username}</div>
                      {u.email && <div className="text-slate-400 text-[11px]">{u.email}</div>}
                    </td>
                    <td className="p-3 text-slate-700">{u.name || "-"}</td>
                    <td className="p-3">
                      {u.status === "pending" ? (
                        <span className="px-2 py-1 bg-amber-100 text-amber-800 rounded font-semibold text-[10px]">
                          ⏳ Chờ duyệt
                        </span>
                      ) : (
                        <span className="px-2 py-1 bg-emerald-100 text-emerald-800 rounded font-semibold text-[10px]">
                          ✅ Đã duyệt
                        </span>
                      )}
                      {u.is_active === 0 && (
                        <span className="ml-1.5 px-2 py-1 bg-rose-100 text-rose-800 rounded font-semibold text-[10px]">
                          🔒 Khóa
                        </span>
                      )}
                    </td>
                    <td className="p-3 text-slate-600">
                      <div><span className="font-semibold">Role:</span> {u.role}</div>
                      {u.scope_value && <div><span className="font-semibold">Vùng:</span> {u.scope_value}</div>}
                      {u.scope_channel && <div><span className="font-semibold">Kênh:</span> {u.scope_channel}</div>}
                      {u.employee_code && <div><span className="font-semibold">Mã NV:</span> {u.employee_code}</div>}
                    </td>
                    <td className="p-3 text-right space-x-2">
                      <button
                        onClick={() => {
                          setSelectedUser(u);
                          setRole(u.role || "qlv");
                          setScopeValue(u.scope_value || "");
                          setEmployeeCode(u.employee_code || "");
                          setScopeChannel(u.scope_channel || "");
                        }}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold text-[11px] shadow-sm"
                      >
                        {u.status === "pending" ? "Phê duyệt ⚙️" : "Sửa quyền ⚙️"}
                      </button>
                      <button
                        onClick={() => handleToggleActive(u.username)}
                        className={`px-2.5 py-1.5 rounded font-semibold text-[11px] border ${
                          u.is_active === 1
                            ? "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100"
                            : "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                        }`}
                      >
                        {u.is_active === 1 ? "Khóa 🔒" : "Mở 🔓"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Modal Phê Duyệt / Gán Quyền */}
        {selectedUser && (
          <div className="p-5 bg-slate-900 text-white border-t border-slate-800">
            <h3 className="text-sm font-bold text-emerald-400 mb-3">
              ⚙️ Cấu hình Phân quyền cho: <span className="text-white">{selectedUser.username}</span> ({selectedUser.email})
            </h3>
            <form onSubmit={handleApprove} className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
              <div>
                <label className="block text-xs text-slate-300 mb-1 font-medium">Vai trò (Role)</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full p-2 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="qlv">QLV (Quản lý vùng / TDV)</option>
                  <option value="regional_director">Regional Director (Giám đốc Miền / Kênh)</option>
                  <option value="c_level">C-Level (Tổng Giám Đốc)</option>
                  <option value="admin_ops">Admin Vận Hành (Hệ thống)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1 font-medium">Phụ trách Vùng</label>
                <select
                  value={scopeValue}
                  onChange={(e) => setScopeValue(e.target.value)}
                  disabled={role === "c_level" || role === "admin_ops"}
                  className="w-full p-2 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                >
                  <option value="">-- Tất cả / Không --</option>
                  <option value="MB">Miền Bắc (MB)</option>
                  <option value="MT">Miền Trung (MT)</option>
                  <option value="MN">Miền Nam (MN)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1 font-medium">Phụ trách Kênh</label>
                <select
                  value={scopeChannel}
                  onChange={(e) => setScopeChannel(e.target.value)}
                  disabled={role === "c_level" || role === "admin_ops"}
                  className="w-full p-2 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                >
                  <option value="">-- Tất cả / Không --</option>
                  <option value="OTC">Kênh Nhà thuốc (OTC)</option>
                  <option value="ETC">Kênh Bệnh viện (ETC)</option>
                </select>
              </div>

              {role === "qlv" && (
                <div>
                  <label className="block text-xs text-slate-300 mb-1 font-medium">Mã Nhân Viên Bravo (Employee Code)</label>
                  <input
                    type="text"
                    placeholder="VD: MBKV1"
                    value={employeeCode}
                    onChange={(e) => setEmployeeCode(e.target.value)}
                    className="w-full p-2 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
              )}

              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded text-xs shadow transition disabled:opacity-50"
                >
                  {actionLoading ? "Đang lưu..." : "Xác nhận Phê Duyệt ✅"}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedUser(null)}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs"
                >
                  Hủy
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Modal Tạo Tài Khoản Mới Trực Tiếp cho Admin C-Level */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-md z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden border border-slate-200">
              <div className="bg-gradient-to-r from-blue-700 to-emerald-600 text-white p-5 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-base">➕ Tạo Tài khoản Mới cho Nhân viên</h3>
                  <p className="text-xs text-white/80">Khởi tạo trực tiếp & Tự động gửi mật khẩu qua Outlook</p>
                </div>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="text-white/80 hover:text-white font-bold text-lg"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleCreateUserSubmit} className="p-6 space-y-4 text-xs">
                {createMsg && (
                  <div
                    className={`p-3.5 rounded-lg font-medium ${
                      createMsg.type === "success"
                        ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                        : "bg-rose-50 text-rose-800 border border-rose-200"
                    }`}
                  >
                    <div>{createMsg.text}</div>
                    {createMsg.pwd && (
                      <div className="mt-2 p-2 bg-white rounded border border-emerald-300 font-mono text-sm font-bold text-emerald-700">
                        🔑 Mật khẩu vừa sinh: <span className="select-all">{createMsg.pwd}</span>
                      </div>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Tên đăng nhập (Username) <span className="text-rose-500">*</span></label>
                    <input
                      type="text"
                      required
                      placeholder="Ví dụ: vui.hoangthi"
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Mật khẩu (Tùy chọn)</label>
                    <input
                      type="text"
                      placeholder="Để trống tự sinh mật khẩu"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Họ và tên nhân viên (Tùy chọn)</label>
                    <input
                      type="text"
                      placeholder="Ví dụ: Hoàng Thị Vui"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Email nhận mật khẩu (Tùy chọn)</label>
                    <input
                      type="email"
                      placeholder="vui.hoangthi@namhapharma.com"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Vai trò (Role)</label>
                    <select
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    >
                      <option value="qlv">QLV (Quản lý vùng / TDV)</option>
                      <option value="regional_director">Regional Director (Giám đốc Vùng / Kênh)</option>
                      <option value="c_level">C-Level (Tổng Giám Đốc)</option>
                      <option value="admin_ops">Admin Vận Hành (Hệ thống)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Phụ trách Vùng</label>
                    <select
                      value={newScopeValue}
                      onChange={(e) => setNewScopeValue(e.target.value)}
                      disabled={newRole === "c_level"}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600 disabled:bg-slate-100"
                    >
                      <option value="">-- Tất cả / Không --</option>
                      <option value="MB">Miền Bắc (MB)</option>
                      <option value="MT">Miền Trung (MT)</option>
                      <option value="MN">Miền Nam (MN)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Phụ trách Kênh</label>
                    <select
                      value={newScopeChannel}
                      onChange={(e) => setNewScopeChannel(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    >
                      <option value="">-- Tất cả / Không --</option>
                      <option value="OTC">Kênh Nhà thuốc (OTC)</option>
                      <option value="ETC">Kênh Bệnh viện (ETC)</option>
                    </select>
                  </div>
                </div>

                {newRole === "qlv" && (
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Mã Nhân Viên Bravo (Employee Code)</label>
                    <input
                      type="text"
                      placeholder="VD: MBKV1"
                      value={newEmployeeCode}
                      onChange={(e) => setNewEmployeeCode(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:border-blue-600"
                    />
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold"
                  >
                    Đóng
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow disabled:opacity-50"
                  >
                    {actionLoading ? "Đang khởi tạo..." : "Tạo Tài Khoản & Gửi Mail 📩"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
