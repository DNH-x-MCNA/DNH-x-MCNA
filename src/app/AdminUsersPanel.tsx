"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  IconShield, IconPlus, IconClose, IconUsers, IconShieldLock, IconRefresh,
  IconClipboard, IconClock, IconCheck, IconLock, IconUnlock, IconKey,
  IconSettings, IconMail, IconSearch,
} from "./icons";
import { useModal } from "./useModal";
import { ExportableTable } from "./TableExport";
import { getRoleLabel, ROLE_LABELS } from "./roleLabels";

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
  password_changed_at?: string | null;
  last_login_at?: string | null;
}

interface AdminUsersPanelProps {
  authToken: string;
  currentRole: string;
  onClose: () => void;
}

// Phan loai theo tien to `sql` ma backend da ghi (<auth:...>/<admin:...>) - dung hon la doan tu
// khoa tren `question` (isPasswordChange/isLogin/isReset ben duoi) vi khong phu thuoc emoji/cau chu.
const SEC_EVENT_CATEGORIES: { value: string; label: string; match: (sql: string) => boolean }[] = [
  { value: "all", label: "Tất cả sự kiện", match: () => true },
  { value: "login", label: "Đăng nhập", match: (sql) => sql === "<auth:login>" },
  { value: "change_password", label: "Đổi mật khẩu", match: (sql) => sql === "<auth:change_password>" },
  { value: "forgot_password", label: "Quên / Reset mật khẩu", match: (sql) => sql.startsWith("<auth:forgot_password") },
  { value: "create_user", label: "Tạo tài khoản", match: (sql) => sql === "<auth:create_user>" || sql === "<admin:create_user>" },
  { value: "approve_user", label: "Phê duyệt tài khoản", match: (sql) => sql === "<admin:approve_user>" },
  { value: "toggle_active", label: "Khóa / Mở khóa tài khoản", match: (sql) => sql === "<admin:toggle_active>" },
  { value: "reset_password", label: "Admin cấp lại mật khẩu", match: (sql) => sql === "<admin:reset_password>" },
];

export default function AdminUsersPanel({ authToken, currentRole, onClose }: AdminUsersPanelProps) {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<UserItem | null>(null);
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);

  // Form phê duyệt state
  const [actionError, setActionError] = useState<string | null>(null);
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
  const [resettingUsername, setResettingUsername] = useState<string | null>(null);
  const [resetMsg, setResetMsg] = useState<{
    text: string;
    type: "success" | "error";
  } | null>(null);

  // Active Tab state inside Admin Users Panel
  const [activeTab, setActiveTab] = useState<"users" | "security">("users");
  const [securityLogs, setSecurityLogs] = useState<any[]>([]);
  const [logsLoading, setLogsLoading] = useState<boolean>(false);
  // Bo loc phia client cho tab Nhat ky bao mat (03/08/2026 -> 06/08/2026: them tim kiem/loc theo
  // su kien/ngay) - khong can goi lai backend, 90 ngay du lieu da tai san co du de loc tai cho.
  const [secSearch, setSecSearch] = useState<string>("");
  const [secEventFilter, setSecEventFilter] = useState<string>("all");
  const [secDateFilter, setSecDateFilter] = useState<string>("");

  const fetchSecurityLogs = async () => {
    setLogsLoading(true);
    try {
      const res = await fetch("/api/audit-logs?days=90", {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await res.json();
      if (res.ok && data.logs) {
        const sec = data.logs.filter((l: any) => {
          const q = (l.question || "").toLowerCase();
          const sql = (l.sql || "").toLowerCase();
          return (
            sql.startsWith("<auth:") ||
            sql.startsWith("<admin:") ||
            q.includes("đổi mật khẩu") ||
            q.includes("đăng nhập") ||
            q.includes("reset") ||
            q.includes("quên") ||
            q.includes("tạo tài khoản") ||
            q.includes("phê duyệt") ||
            q.includes("khóa")
          );
        });
        setSecurityLogs(sec);
      }
    } catch (err: any) {
      console.error("Lỗi tải nhật ký bảo mật:", err);
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "security") {
      fetchSecurityLogs();
    }
  }, [activeTab]);

  const filteredSecurityLogs = useMemo(() => {
    const cat = SEC_EVENT_CATEGORIES.find((c) => c.value === secEventFilter) || SEC_EVENT_CATEGORIES[0];
    const q = secSearch.trim().toLowerCase();
    return securityLogs.filter((log: any) => {
      if (!cat.match(log.sql || "")) return false;
      if (secDateFilter && (log.ts || "").slice(0, 10) !== secDateFilter) return false;
      if (q) {
        const hay = `${log.username || ""} ${log.user_name || ""} ${log.question || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [securityLogs, secEventFilter, secDateFilter, secSearch]);

  const secFiltersActive = secEventFilter !== "all" || Boolean(secDateFilter) || Boolean(secSearch.trim());

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
    setActionError(null);
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
      setActionError(err.message);
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
    setActionError(null);
    try {
      const res = await fetch(`/api/admin/users/${encodeURIComponent(username)}/toggle-active`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Thao tác thất bại");
      fetchUsers();
    } catch (err: any) {
      setActionError(err.message);
    }
  };

  const handleResetPassword = async (target: UserItem) => {
    const confirmed = window.confirm(
      `Đặt lại mật khẩu cho ${target.username}? Mọi phiên đăng nhập hiện tại của tài khoản này sẽ bị thu hồi.`,
    );
    if (!confirmed) return;

    setResettingUsername(target.username);
    setResetMsg(null);
    try {
      const res = await fetch(
        `/api/admin/users/${encodeURIComponent(target.username)}/reset-password`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${authToken}` },
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Đặt lại mật khẩu thất bại");
      setResetMsg({
        text: data.message || "Đã đặt lại mật khẩu.",
        type: "success",
      });
      fetchUsers();
    } catch (err: unknown) {
      setResetMsg({
        text: err instanceof Error ? err.message : "Đặt lại mật khẩu thất bại",
        type: "error",
      });
    } finally {
      setResettingUsername(null);
    }
  };

  // Tam dung bay focus/Escape cua khung chinh khi modal tao tai khoan (long ben trong) dang mo,
  // de Escape/Tab chi tac dong len modal tren cung, tranh 2 modal cung phan hoi 1 luc.
  const panelRef = useModal(!showCreateModal, onClose);
  const createModalRef = useModal(showCreateModal, () => setShowCreateModal(false));

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-panel-title"
        tabIndex={-1}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl border border-slate-200 overflow-hidden my-8 outline-none"
      >
        {/* Header */}
        <div className="bg-slate-900 text-white p-5 flex items-center justify-between">
          <div>
            <h2 id="admin-panel-title" className="text-lg font-bold flex items-center gap-2"><IconShield className="w-5 h-5" /> Quản lý & Phê duyệt Tài khoản Nhân viên</h2>
            <p className="text-xs text-slate-400">
              {currentRole === "admin_ops"
                ? "Admin Vận Hành: quản lý trạng thái và cấp lại mật khẩu qua email"
                : "C-Level: tạo, phê duyệt và phân quyền tài khoản"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {currentRole === "c_level" && (
              <button
                onClick={() => { setShowCreateModal(true); setCreateMsg(null); }}
                className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold text-xs shadow-md transition flex items-center gap-1.5"
              >
                <IconPlus className="w-3.5 h-3.5" /> Tạo Tài khoản Mới
              </button>
            )}
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center font-bold text-sm transition"
            >
              <IconClose className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Top Navigation Tabs Bar */}
        <div className="bg-slate-100 border-b border-slate-200 px-5 py-2.5 flex items-center justify-between">
          <div className="flex gap-2 text-xs font-semibold">
            <button
              onClick={() => setActiveTab("users")}
              className={`px-4 py-2 rounded-xl transition flex items-center gap-1.5 ${
                activeTab === "users"
                  ? "bg-indigo-600 text-white shadow-sm font-bold"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              <IconUsers className="w-3.5 h-3.5" /> Danh sách & Quyền Tài khoản
            </button>
            <button
              onClick={() => setActiveTab("security")}
              className={`px-4 py-2 rounded-xl transition flex items-center gap-1.5 ${
                activeTab === "security"
                  ? "bg-purple-600 text-white shadow-sm font-bold"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              <IconShieldLock className="w-3.5 h-3.5" /> Nhật ký Đổi MK & Đăng nhập ({securityLogs.length})
            </button>
          </div>
          {activeTab === "security" && (
            <button
              onClick={fetchSecurityLogs}
              className="text-xs font-semibold text-purple-700 hover:text-purple-900 bg-purple-50 px-3 py-1.5 rounded-lg border border-purple-200 flex items-center gap-1.5"
            >
              <IconRefresh className="w-3.5 h-3.5" /> Tải lại Nhật ký
            </button>
          )}
        </div>

        {actionError && (
          <div className="mx-5 mt-3 p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-lg flex items-center justify-between gap-2">
            <span>Lỗi: {actionError}</span>
            <button onClick={() => setActionError(null)} className="text-rose-500 hover:text-rose-700 shrink-0">
              <IconClose className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Filter Bar & Content Table for Users Tab */}
        {activeTab === "users" && (
          <>
            <div className="bg-slate-50 border-b border-slate-200 p-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-600">Lọc trạng thái:</span>
                <button
                  onClick={() => setFilterStatus("")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                    filterStatus === ""
                      ? "bg-blue-600 text-white shadow-sm"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <IconClipboard className="w-3.5 h-3.5" /> Tất cả tài khoản
                </button>
                <button
                  onClick={() => setFilterStatus("pending")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                    filterStatus === "pending"
                      ? "bg-amber-600 text-white shadow-sm"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <IconClock className="w-3.5 h-3.5" /> Chờ duyệt (Pending)
                </button>
                <button
                  onClick={() => setFilterStatus("approved")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                    filterStatus === "approved"
                      ? "bg-emerald-600 text-white shadow-sm"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <IconCheck className="w-3.5 h-3.5" /> Đã duyệt (Approved)
                </button>
              </div>

              <button
                onClick={fetchUsers}
                className="text-xs font-semibold text-blue-700 hover:text-blue-900 bg-blue-50 px-3 py-1.5 rounded-lg border border-blue-200 flex items-center gap-1.5"
              >
                <IconRefresh className="w-3.5 h-3.5" /> Tải lại
              </button>
            </div>

            {/* Content Table */}
            <div className="p-5 max-h-[60vh] overflow-y-auto">
              {error && <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg mb-4">{error}</div>}
              {resetMsg && (
                <div
                  className={`mb-4 rounded-lg border p-3 text-xs font-medium ${
                    resetMsg.type === "success"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : "border-rose-200 bg-rose-50 text-rose-800"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div>{resetMsg.text}</div>
                      {resetMsg.type === "success" && (
                        <div className="mt-1 text-[11px] font-normal">
                          Đã gửi mật khẩu tạm tới email công ty của người dùng. Admin không nhìn thấy mật khẩu.
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setResetMsg(null)}
                      className="shrink-0 text-slate-500 hover:text-slate-800"
                      aria-label="Đóng thông báo đặt lại mật khẩu"
                    >
                      <IconClose className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}

              {loading ? (
                <div className="py-12 text-center text-slate-500 text-sm">Đang tải danh sách tài khoản...</div>
              ) : users.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-sm">Không có tài khoản nào phù hợp với bộ lọc.</div>
              ) : (
                <ExportableTable nhan="danh-sach-tai-khoan">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50">
                      <th className="p-3">Tài khoản / Email</th>
                      <th className="p-3">Họ tên</th>
                      <th className="p-3">Trạng thái</th>
                      <th className="p-3">Vai trò & Phạm vi</th>
                      <th className="p-3">Hoạt động (Login / Đổi MK)</th>
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
                            <span className="px-2 py-1 bg-amber-100 text-amber-800 rounded font-semibold text-[10px] inline-flex items-center gap-1">
                              <IconClock className="w-3 h-3" /> Chờ duyệt
                            </span>
                          ) : (
                            <span className="px-2 py-1 bg-emerald-100 text-emerald-800 rounded font-semibold text-[10px] inline-flex items-center gap-1">
                              <IconCheck className="w-3 h-3" /> Đã duyệt
                            </span>
                          )}
                          {u.is_active === 0 && (
                            <span className="ml-1.5 px-2 py-1 bg-rose-100 text-rose-800 rounded font-semibold text-[10px] inline-flex items-center gap-1">
                              <IconLock className="w-3 h-3" /> Khóa
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-slate-600">
                          <div><span className="font-semibold">Vai trò:</span> {getRoleLabel(u.role)}</div>
                          {u.scope_value && <div><span className="font-semibold">Vùng:</span> {u.scope_value}</div>}
                          {u.scope_channel && <div><span className="font-semibold">Kênh:</span> {u.scope_channel}</div>}
                          {u.employee_code && <div><span className="font-semibold">Mã NV:</span> {u.employee_code}</div>}
                        </td>
                        <td className="p-3 text-[11px] text-slate-600">
                          {u.last_login_at ? (
                            <div className="font-medium text-emerald-700 flex items-center gap-1"><IconClock className="w-3 h-3" /> Login: {u.last_login_at.slice(0, 16).replace("T", " ")}</div>
                          ) : (
                            <div className="text-slate-400 flex items-center gap-1"><IconClock className="w-3 h-3" /> Chưa login</div>
                          )}
                          {u.password_changed_at ? (
                            <div className="font-medium text-amber-700 flex items-center gap-1"><IconKey className="w-3 h-3" /> Đổi MK: {u.password_changed_at.slice(0, 16).replace("T", " ")}</div>
                          ) : (
                            <div className="text-slate-400 flex items-center gap-1"><IconKey className="w-3 h-3" /> MK khởi tạo</div>
                          )}
                        </td>
                        <td className="p-3 text-right space-x-2">
                          {currentRole === "c_level" && (
                            <button
                              onClick={() => {
                                setSelectedUser(u);
                                setRole(u.role || "qlv");
                                setScopeValue(u.scope_value || "");
                                setEmployeeCode(u.employee_code || "");
                                setScopeChannel(u.scope_channel || "");
                              }}
                              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold text-[11px] shadow-sm inline-flex items-center gap-1"
                            >
                              {u.status === "pending" ? "Phê duyệt" : "Sửa quyền"} <IconSettings className="w-3 h-3" />
                            </button>
                          )}
                          {currentRole === "admin_ops" && !["c_level", "admin_ops"].includes(u.role) && (
                            <button
                              onClick={() => handleResetPassword(u)}
                              disabled={resettingUsername === u.username}
                              className="px-2.5 py-1.5 rounded font-semibold text-[11px] border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:cursor-wait disabled:opacity-50 inline-flex items-center gap-1"
                            >
                              {resettingUsername === u.username ? "Đang gửi..." : "Cấp lại MK"}
                              <IconKey className="w-3 h-3" />
                            </button>
                          )}
                          {!(currentRole === "admin_ops" && ["c_level", "admin_ops"].includes(u.role)) && (
                            <button
                              onClick={() => handleToggleActive(u.username)}
                              className={`px-2.5 py-1.5 rounded font-semibold text-[11px] border inline-flex items-center gap-1 ${
                                u.is_active === 1
                                  ? "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100"
                                  : "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                              }`}
                            >
                              {u.is_active === 1 ? (<>Khóa <IconLock className="w-3 h-3" /></>) : (<>Mở <IconUnlock className="w-3 h-3" /></>)}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </ExportableTable>
              )}
            </div>
          </>
        )}

        {/* Security Logs Tab View */}
        {activeTab === "security" && (
          <div className="p-5 max-h-[60vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <IconShieldLock className="w-3.5 h-3.5" /> Lịch sử Đổi Mật Khẩu, Đăng Nhập & Thao Tác Quản Trị ({filteredSecurityLogs.length}
                {filteredSecurityLogs.length !== securityLogs.length ? ` / ${securityLogs.length}` : ""} sự kiện)
              </h3>
              <span className="text-[11px] text-slate-500">Tự động đồng bộ từ database & audit log</span>
            </div>

            {/* Filter Bar: tim kiem, loai su kien, ngay cu the */}
            <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="relative flex-1 min-w-[180px]">
                <IconSearch className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={secSearch}
                  onChange={(e) => setSecSearch(e.target.value)}
                  placeholder="Tìm theo tài khoản, họ tên, nội dung..."
                  className="w-full rounded-lg border border-slate-300 bg-white py-1.5 pl-8 pr-2.5 text-xs text-slate-800 outline-none transition focus:border-purple-400 focus:ring-2 focus:ring-purple-100"
                />
              </div>
              <select
                value={secEventFilter}
                onChange={(e) => setSecEventFilter(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 outline-none transition focus:border-purple-400 focus:ring-2 focus:ring-purple-100"
              >
                {SEC_EVENT_CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
              <input
                type="date"
                value={secDateFilter}
                onChange={(e) => setSecDateFilter(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 outline-none transition focus:border-purple-400 focus:ring-2 focus:ring-purple-100"
              />
              {secFiltersActive && (
                <button
                  onClick={() => {
                    setSecSearch("");
                    setSecEventFilter("all");
                    setSecDateFilter("");
                  }}
                  className="flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                >
                  <IconClose className="h-3 w-3" /> Xóa lọc
                </button>
              )}
            </div>

            {logsLoading ? (
              <div className="py-12 text-center text-slate-500 text-sm">Đang tải nhật ký bảo mật...</div>
            ) : securityLogs.length === 0 ? (
              <div className="py-12 text-center text-slate-400 text-sm">Chưa có dữ liệu nhật ký bảo mật.</div>
            ) : filteredSecurityLogs.length === 0 ? (
              <div className="py-12 text-center text-slate-400 text-sm">Không có sự kiện nào khớp với bộ lọc hiện tại.</div>
            ) : (
              <ExportableTable nhan="nhat-ky-bao-mat">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50">
                    <th className="p-3">Thời gian</th>
                    <th className="p-3">Tài khoản</th>
                    <th className="p-3">Họ tên</th>
                    <th className="p-3">Nội dung thao tác / Sự kiện</th>
                    <th className="p-3 text-center">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredSecurityLogs.map((log: any, idx: number) => {
                    const isError = log.status === "error";
                    const qText = log.question || "";
                    const isPasswordChange = qText.includes("Đổi mật khẩu");
                    const isLogin = qText.includes("Đăng nhập");
                    const isReset = qText.includes("Reset") || qText.includes("Quên");
                    return (
                      <tr key={idx} className="hover:bg-slate-50/80 transition">
                        <td className="p-3 font-mono text-slate-600 whitespace-nowrap">
                          {log.ts ? log.ts.replace("T", " ").slice(0, 19) : "—"}
                        </td>
                        <td className="p-3 font-semibold text-slate-900 whitespace-nowrap">
                          {log.username}
                        </td>
                        <td className="p-3 text-slate-700 whitespace-nowrap">
                          {log.user_name}
                        </td>
                        <td className="p-3 font-medium">
                          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
                            isPasswordChange
                              ? "bg-amber-100 text-amber-900 border border-amber-300"
                              : isLogin
                              ? "bg-emerald-100 text-emerald-900 border border-emerald-300"
                              : isReset
                              ? "bg-purple-100 text-purple-900 border border-purple-300"
                              : "bg-blue-100 text-blue-900 border border-blue-300"
                          }`}>
                            {qText}
                          </span>
                        </td>
                        <td className="p-3 text-center whitespace-nowrap">
                          {isError ? (
                            <span className="px-2 py-0.5 bg-rose-100 text-rose-800 rounded font-semibold text-[10px]">Thất bại</span>
                          ) : (
                            <span className="px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded font-semibold text-[10px]">Thành công</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              </ExportableTable>
            )}
          </div>
        )}

        {/* Modal Phê Duyệt / Gán Quyền */}
        {selectedUser && (
          <div className="p-5 bg-slate-900 text-white border-t border-slate-800">
            <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-1.5">
              <IconSettings className="w-4 h-4" /> Cấu hình Phân quyền cho: <span className="text-white">{selectedUser.username}</span> ({selectedUser.email})
            </h3>
            <form onSubmit={handleApprove} className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
              <div>
                <label className="block text-xs text-slate-300 mb-1 font-medium">Vai trò (Role)</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full p-2 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="qlv">{ROLE_LABELS.qlv}</option>
                  <option value="regional_director">{ROLE_LABELS.regional_director}</option>
                  <option value="c_level">{ROLE_LABELS.c_level}</option>
                  <option value="admin_ops">{ROLE_LABELS.admin_ops}</option>
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
                  className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded text-xs shadow transition disabled:opacity-50 flex items-center justify-center gap-1.5"
                >
                  {actionLoading ? "Đang lưu..." : (<>Xác nhận Phê Duyệt <IconCheck className="w-3.5 h-3.5" /></>)}
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
            <div
              ref={createModalRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-user-title"
              tabIndex={-1}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden border border-slate-200 outline-none"
            >
              <div className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white p-5 flex items-center justify-between">
                <div>
                  <h3 id="create-user-title" className="font-bold text-base flex items-center gap-1.5"><IconPlus className="w-4 h-4" /> Tạo Tài khoản Mới cho Nhân viên</h3>
                  <p className="text-xs text-white/80">Khởi tạo trực tiếp & Tự động gửi mật khẩu qua Outlook</p>
                </div>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="text-white/80 hover:text-white font-bold text-lg"
                >
                  <IconClose className="w-4 h-4" />
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
                      <div className="mt-2 p-2 bg-white rounded border border-emerald-300 font-mono text-sm font-bold text-emerald-700 flex items-center gap-1.5">
                        <IconKey className="w-4 h-4 shrink-0" /> Mật khẩu vừa sinh: <span className="select-all">{createMsg.pwd}</span>
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
                      <option value="qlv">{ROLE_LABELS.qlv}</option>
                      <option value="regional_director">{ROLE_LABELS.regional_director}</option>
                      <option value="c_level">{ROLE_LABELS.c_level}</option>
                      <option value="admin_ops">{ROLE_LABELS.admin_ops}</option>
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
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {actionLoading ? "Đang khởi tạo..." : (<>Tạo Tài Khoản & Gửi Mail <IconMail className="w-4 h-4" /></>)}
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
