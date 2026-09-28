"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { IconClose, IconCopy, IconRefresh, IconSearch, IconShieldLock, IconUserPlus, IconUsers } from "./icons";
import { formatDateTime } from "./lib";
import { getRoleLabel, ROLE_LABELS } from "./roleLabels";
import { ExportableTable } from "./TableExport";
import {
  Badge, Button, CompactInput, ConfirmDialog, Dialog, DialogBody, DialogFooter, DialogHeader, Field, IconButton,
  Notice, SegmentedControl, Select, Skeleton, TextInput, cx,
} from "./ui";

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

type SecurityLog = {
  ts?: string;
  username?: string;
  user_name?: string;
  question?: string;
  sql?: string | null;
  status?: string;
};

interface AdminUsersPanelProps {
  authToken: string;
  /** Vai tro NGUOI DANG THAO TAC: c_level tao/phe duyet/phan quyen; admin_ops khoa-mo va cap lai mat khau. */
  currentRole: string;
  onClose: () => void;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

// Phan loai theo tien to `sql` ma backend da ghi (<auth:...>/<admin:...>) - dung hon la doan tu
// khoa tren `question` vi khong phu thuoc emoji/cau chu.
const SEC_EVENT_CATEGORIES: { value: string; label: string; tone: "neutral" | "brand" | "warning" | "success"; match: (sql: string) => boolean }[] = [
  { value: "all", label: "Tất cả sự kiện", tone: "neutral", match: () => true },
  { value: "login", label: "Đăng nhập", tone: "success", match: (sql) => sql === "<auth:login>" },
  { value: "change_password", label: "Đổi mật khẩu", tone: "brand", match: (sql) => sql === "<auth:change_password>" },
  { value: "forgot_password", label: "Quên / Reset mật khẩu", tone: "warning", match: (sql) => sql.startsWith("<auth:forgot_password") },
  { value: "create_user", label: "Tạo tài khoản", tone: "neutral", match: (sql) => sql === "<auth:create_user>" || sql === "<admin:create_user>" },
  { value: "approve_user", label: "Phê duyệt tài khoản", tone: "neutral", match: (sql) => sql === "<admin:approve_user>" },
  { value: "toggle_active", label: "Khóa / Mở khóa tài khoản", tone: "neutral", match: (sql) => sql === "<admin:toggle_active>" },
  { value: "reset_password", label: "Admin cấp lại mật khẩu", tone: "warning", match: (sql) => sql === "<admin:reset_password>" },
];

const REGION_OPTIONS = [
  { value: "MB", label: "Miền Bắc (MB)" },
  { value: "MT", label: "Miền Trung (MT)" },
  { value: "MN", label: "Miền Nam (MN)" },
];
const CHANNEL_OPTIONS = [
  { value: "OTC", label: "Kênh Nhà thuốc (OTC)" },
  { value: "ETC", label: "Kênh Bệnh viện (ETC)" },
];
const REGION_SHORT: Record<string, string> = { MB: "Miền Bắc", MT: "Miền Trung", MN: "Miền Nam" };
const PRIVILEGED_ROLES = ["c_level", "admin_ops"];

// Noi dung su kien backend ghi san emoji o dau ("🔐 Dang nhap...") - bo di cho bang gon, chu giu nguyen.
function stripLeadingEmoji(text: string): string {
  return text.replace(/^[\p{Extended_Pictographic}️‍\s]+/u, "");
}

export default function AdminUsersPanel({ authToken, currentRole, onClose }: AdminUsersPanelProps) {
  const isCLevel = currentRole === "c_level";
  const isOps = currentRole === "admin_ops";
  const [users, setUsers] = useState<UserItem[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<UserItem | null>(null);
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [resetTarget, setResetTarget] = useState<UserItem | null>(null);
  const [resettingUsername, setResettingUsername] = useState<string | null>(null);
  const [resetMsg, setResetMsg] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const [activeTab, setActiveTab] = useState<"users" | "security">("users");
  const [securityLogs, setSecurityLogs] = useState<SecurityLog[]>([]);
  const [logsLoading, setLogsLoading] = useState<boolean>(false);
  // Bo loc phia client cho tab Nhat ky bao mat - khong can goi lai backend, 90 ngay du lieu da tai
  // san co du de loc tai cho.
  const [secSearch, setSecSearch] = useState<string>("");
  const [secEventFilter, setSecEventFilter] = useState<string>("all");
  const [secDateFilter, setSecDateFilter] = useState<string>("");

  const fetchSecurityLogs = async () => {
    setLogsLoading(true);
    await requestSecurityLogs();
  };

  const requestSecurityLogs = async () => {
    try {
      const res = await fetch("/api/audit-logs?days=90", { headers: { Authorization: `Bearer ${authToken}` } });
      const data = await res.json();
      if (res.ok && data.logs) {
        const sec = (data.logs as SecurityLog[]).filter((l) => {
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
    } catch (err) {
      console.error("Lỗi tải nhật ký bảo mật:", err);
    } finally {
      setLogsLoading(false);
    }
  };

  function changeTab(next: "users" | "security") {
    setActiveTab(next);
    if (next === "security") fetchSecurityLogs();
  }

  const filteredSecurityLogs = useMemo(() => {
    const cat = SEC_EVENT_CATEGORIES.find((c) => c.value === secEventFilter) || SEC_EVENT_CATEGORIES[0];
    const q = secSearch.trim().toLowerCase();
    return securityLogs.filter((log) => {
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

  // requestUsers chi goi API; co "dang tai" do noi goi bat truoc (luc mount thi san la true).
  const requestUsers = (status: string) => {
    const url = status ? `/api/admin/users?status=${status}` : "/api/admin/users";
    fetch(url, { headers: { Authorization: `Bearer ${authToken}` } })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Không thể tải danh sách tài khoản");
        setUsers(data);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Không thể tải danh sách tài khoản")))
      .finally(() => setLoading(false));
  };

  const fetchUsers = (status: string = filterStatus) => {
    setLoading(true);
    setError(null);
    requestUsers(status);
  };

  function changeFilter(status: string) {
    setFilterStatus(status);
    fetchUsers(status);
  }

  useEffect(() => {
    requestUsers("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    } catch (err) {
      setActionError(errorMessage(err, "Thao tác thất bại"));
    }
  };

  // Admin Van Hanh cap lai mat khau: backend sinh mat khau tam va gui thang toi email cong ty cua nguoi
  // dung - admin khong nhin thay mat khau. Moi phien hien tai cua tai khoan do bi thu hoi.
  const handleResetPassword = async (target: UserItem) => {
    setResetTarget(null);
    setResettingUsername(target.username);
    setResetMsg(null);
    try {
      const res = await fetch(`/api/admin/users/${encodeURIComponent(target.username)}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Đặt lại mật khẩu thất bại");
      setResetMsg({ text: data.message || "Đã đặt lại mật khẩu.", type: "success" });
      fetchUsers();
    } catch (err) {
      setResetMsg({ text: errorMessage(err, "Đặt lại mật khẩu thất bại"), type: "error" });
    } finally {
      setResettingUsername(null);
    }
  };

  const pendingCount = users.filter((u) => u.status === "pending").length;
  const childOpen = showCreateModal || Boolean(selectedUser) || Boolean(resetTarget);

  return (
    <>
      <Dialog open onClose={onClose} labelledBy="admin-panel-title" size="full" trap={!childOpen} className="sm:h-[88vh]">
        <DialogHeader
          id="admin-panel-title"
          icon={<IconUsers className="h-[18px] w-[18px]" />}
          title="Tài khoản nhân viên"
          description={isOps
            ? "Admin Vận Hành: khóa/mở tài khoản và cấp lại mật khẩu qua email · xem nhật ký bảo mật"
            : "Tạo, phê duyệt và phân quyền tài khoản · xem nhật ký bảo mật"}
          onClose={onClose}
          actions={isCLevel && (
            <Button variant="primary" size="sm" icon={<IconUserPlus className="h-4 w-4" />} onClick={() => setShowCreateModal(true)}>
              Tạo tài khoản
            </Button>
          )}
        />

        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3 sm:px-6">
          <SegmentedControl<"users" | "security">
            label="Chế độ xem"
            value={activeTab}
            onChange={changeTab}
            options={[
              { value: "users", label: "Danh sách tài khoản" },
              { value: "security", label: "Nhật ký bảo mật", badge: securityLogs.length || undefined },
            ]}
          />
          <div className="ml-auto flex items-center gap-2">
            {activeTab === "users" ? (
              <>
                <SegmentedControl<string>
                  label="Lọc trạng thái"
                  value={filterStatus}
                  onChange={changeFilter}
                  options={[
                    { value: "", label: "Tất cả" },
                    { value: "pending", label: "Chờ duyệt", badge: filterStatus === "" && pendingCount ? pendingCount : undefined },
                    { value: "approved", label: "Đã duyệt" },
                  ]}
                />
                <IconButton label="Tải lại danh sách" onClick={() => fetchUsers()} disabled={loading}>
                  <IconRefresh className={cx("h-[18px] w-[18px]", loading && "animate-spin")} />
                </IconButton>
              </>
            ) : (
              <IconButton label="Tải lại nhật ký" onClick={fetchSecurityLogs} disabled={logsLoading}>
                <IconRefresh className={cx("h-[18px] w-[18px]", logsLoading && "animate-spin")} />
              </IconButton>
            )}
            {isCLevel && (
              <Button variant="primary" size="sm" className="sm:hidden" icon={<IconUserPlus className="h-4 w-4" />} onClick={() => setShowCreateModal(true)}>
                Tạo
              </Button>
            )}
          </div>
        </div>

        <DialogBody className="bg-soft/60">
          {actionError && (
            <Notice tone="danger" className="mb-4" action={<Button size="sm" variant="secondary" onClick={() => setActionError(null)}>Đóng thông báo</Button>}>
              {actionError}
            </Notice>
          )}

          {activeTab === "users" ? (
            <>
              {error && <Notice tone="danger" className="mb-4">{error}</Notice>}
              {resetMsg && (
                <Notice
                  tone={resetMsg.type === "success" ? "success" : "danger"}
                  className="mb-4"
                  action={<Button size="sm" variant="secondary" onClick={() => setResetMsg(null)}>Đóng thông báo</Button>}
                >
                  {resetMsg.text}
                  {resetMsg.type === "success" && (
                    <div className="mt-0.5">Đã gửi mật khẩu tạm tới email công ty của người dùng. Admin không nhìn thấy mật khẩu.</div>
                  )}
                </Notice>
              )}
              {loading && users.length === 0 ? (
                <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
              ) : users.length === 0 ? (
                <div className="py-16 text-center text-[14px] text-slate-400">Không có tài khoản nào phù hợp với bộ lọc.</div>
              ) : (
                <ExportableTable nhan="danh-sach-tai-khoan" className="custom-scroll overflow-x-auto rounded-2xl bg-white shadow-card ring-1 ring-inset ring-line">
                  <table className="w-full border-collapse text-left text-[13.5px]">
                    <thead>
                      <tr className="border-b border-line bg-soft text-[12.5px] font-medium text-slate-500">
                        <th className="px-4 py-2.5 font-medium">Tài khoản</th>
                        <th className="px-4 py-2.5 font-medium">Trạng thái</th>
                        <th className="px-4 py-2.5 font-medium">Vai trò & phạm vi</th>
                        <th className="px-4 py-2.5 font-medium">Hoạt động gần nhất</th>
                        <th className="px-4 py-2.5 text-right font-medium">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((u) => {
                        const scope = [
                          u.scope_value ? REGION_SHORT[u.scope_value] || u.scope_value : null,
                          u.scope_channel ? `Kênh ${u.scope_channel}` : null,
                          u.employee_code ? `Mã NV ${u.employee_code}` : null,
                        ].filter(Boolean).join(" · ");
                        // Admin Van Hanh khong dong vao tai khoan C-Level/Admin khac.
                        const opsOnPrivileged = isOps && PRIVILEGED_ROLES.includes(u.role);
                        return (
                          <tr key={u.id} className="border-b border-slate-100 align-top transition-colors last:border-b-0 hover:bg-slate-50/70">
                            <td className="px-4 py-3">
                              <div className="font-medium text-navy">{u.name || u.username}</div>
                              <div className="text-[12.5px] text-slate-500">
                                <span className="font-mono">{u.username}</span>
                                {u.email ? ` · ${u.email}` : ""}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1.5">
                                {u.status === "pending" ? <Badge tone="warning">Chờ duyệt</Badge> : <Badge tone="success">Đã duyệt</Badge>}
                                {u.is_active === 0 && <Badge tone="danger">Đã khóa</Badge>}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="text-slate-800">{getRoleLabel(u.role)}</div>
                              {scope && <div className="text-[12.5px] text-slate-500">{scope}</div>}
                            </td>
                            <td className="px-4 py-3 text-[12.5px] text-slate-500">
                              <div>{u.last_login_at ? `Đăng nhập ${formatDateTime(u.last_login_at)}` : "Chưa đăng nhập lần nào"}</div>
                              <div>{u.password_changed_at ? `Đổi mật khẩu ${formatDateTime(u.password_changed_at)}` : "Vẫn dùng mật khẩu khởi tạo"}</div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex justify-end gap-1.5">
                                {isCLevel && (
                                  <Button size="sm" variant={u.status === "pending" ? "primary" : "secondary"} onClick={() => setSelectedUser(u)}>
                                    {u.status === "pending" ? "Phê duyệt" : "Phân quyền"}
                                  </Button>
                                )}
                                {isOps && !opsOnPrivileged && (
                                  <Button size="sm" variant="secondary" loading={resettingUsername === u.username} onClick={() => setResetTarget(u)}>
                                    {resettingUsername === u.username ? "Đang gửi…" : "Cấp lại mật khẩu"}
                                  </Button>
                                )}
                                {!opsOnPrivileged && (
                                  <Button size="sm" variant={u.is_active === 1 ? "dangerGhost" : "successGhost"} onClick={() => handleToggleActive(u.username)}>
                                    {u.is_active === 1 ? "Khóa" : "Mở khóa"}
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </ExportableTable>
              )}
            </>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-[220px] flex-1">
                  <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <CompactInput value={secSearch} onChange={(e) => setSecSearch(e.target.value)} placeholder="Tìm theo tài khoản, họ tên, nội dung…" className="pl-9" aria-label="Tìm trong nhật ký" />
                </div>
                <Select compact value={secEventFilter} onChange={(e) => setSecEventFilter(e.target.value)} aria-label="Loại sự kiện">
                  {SEC_EVENT_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </Select>
                <CompactInput type="date" value={secDateFilter} onChange={(e) => setSecDateFilter(e.target.value)} aria-label="Ngày" className="w-auto" />
                {secFiltersActive && (
                  <Button size="sm" variant="ghost" icon={<IconClose className="h-3.5 w-3.5" />}
                    onClick={() => { setSecSearch(""); setSecEventFilter("all"); setSecDateFilter(""); }}>
                    Xóa lọc
                  </Button>
                )}
              </div>
              <p className="text-[13px] text-slate-500">
                {filteredSecurityLogs.length}
                {filteredSecurityLogs.length !== securityLogs.length ? ` / ${securityLogs.length}` : ""} sự kiện trong 90 ngày:
                đăng nhập, đổi mật khẩu và thao tác quản trị.
              </p>
              {logsLoading && securityLogs.length === 0 ? (
                <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-11 rounded-xl" />)}</div>
              ) : securityLogs.length === 0 ? (
                <div className="py-16 text-center text-[14px] text-slate-400">Chưa có dữ liệu nhật ký bảo mật.</div>
              ) : filteredSecurityLogs.length === 0 ? (
                <div className="py-16 text-center text-[14px] text-slate-400">Không có sự kiện nào khớp bộ lọc.</div>
              ) : (
                <ExportableTable nhan="nhat-ky-bao-mat" className="custom-scroll overflow-x-auto rounded-2xl bg-white shadow-card ring-1 ring-inset ring-line">
                  <table className="w-full border-collapse text-left text-[13.5px]">
                    <thead>
                      <tr className="border-b border-line bg-soft text-[12.5px] text-slate-500">
                        <th className="px-4 py-2.5 font-medium">Thời gian</th>
                        <th className="px-4 py-2.5 font-medium">Người thực hiện</th>
                        <th className="px-4 py-2.5 font-medium">Sự kiện</th>
                        <th className="px-4 py-2.5 text-right font-medium">Kết quả</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSecurityLogs.map((log, idx) => {
                        const cat = SEC_EVENT_CATEGORIES.slice(1).find((c) => c.match(log.sql || ""));
                        return (
                          <tr key={idx} className="border-b border-slate-100 transition-colors last:border-b-0 hover:bg-slate-50/70">
                            <td className="whitespace-nowrap px-4 py-3 tabular-nums text-slate-500">{formatDateTime(log.ts, true) || "—"}</td>
                            <td className="whitespace-nowrap px-4 py-3">
                              <div className="font-medium text-navy">{log.user_name}</div>
                              <div className="font-mono text-[12px] text-slate-500">{log.username}</div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap items-center gap-2">
                                {cat && <Badge tone={cat.tone}>{cat.label}</Badge>}
                                <span className="text-slate-700">{stripLeadingEmoji(log.question || "")}</span>
                              </div>
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-right">
                              {log.status === "error" ? <Badge tone="danger">Thất bại</Badge> : <Badge tone="success">Thành công</Badge>}
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
        </DialogBody>
      </Dialog>

      {selectedUser && (
        <ApproveDialog
          key={selectedUser.id}
          user={selectedUser}
          authToken={authToken}
          onClose={() => setSelectedUser(null)}
          onSaved={() => { setSelectedUser(null); fetchUsers(); }}
        />
      )}
      <CreateUserDialog
        open={showCreateModal}
        authToken={authToken}
        onClose={() => setShowCreateModal(false)}
        onCreated={() => fetchUsers()}
      />
      <ConfirmDialog
        open={Boolean(resetTarget)}
        title="Cấp lại mật khẩu?"
        message={<>Hệ thống sẽ gửi mật khẩu tạm tới email của <span className="font-medium text-navy">{resetTarget?.username}</span>. Mọi phiên đăng nhập hiện tại của tài khoản này sẽ bị thu hồi.</>}
        confirmLabel="Cấp lại mật khẩu"
        onConfirm={() => resetTarget && handleResetPassword(resetTarget)}
        onCancel={() => setResetTarget(null)}
      />
    </>
  );
}

// Mount rieng cho tung tai khoan (key = id) nen gia tri ban dau lay thang tu tai khoan dang sua.
function ApproveDialog({ user, authToken, onClose, onSaved }: {
  user: UserItem;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [role, setRole] = useState(user.role || "qlv");
  const [scopeValue, setScopeValue] = useState(user.scope_value || "");
  const [employeeCode, setEmployeeCode] = useState(user.employee_code || "");
  const [scopeChannel, setScopeChannel] = useState(user.scope_channel || "");
  const [editEmail, setEditEmail] = useState(user.email || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scopeLocked = role === "c_level" || role === "admin_ops";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${encodeURIComponent(user.username)}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
        body: JSON.stringify({
          role,
          scope_value: scopeLocked ? null : (scopeValue || null),
          employee_code: role === "qlv" ? (employeeCode.trim() || null) : null,
          scope_channel: scopeLocked ? null : (scopeChannel || null),
          // De trong = giu nguyen email hien co. Email la noi nhan mat khau khi "Cap lai mat khau".
          email: editEmail.trim() || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Phê duyệt thất bại");
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Phê duyệt thất bại"));
    } finally {
      setSaving(false);
    }
  }

  const pending = user.status === "pending";
  return (
    <Dialog open onClose={onClose} labelledBy="approve-title" size="md" closeOnBackdrop={false}>
      <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
        <DialogHeader
          id="approve-title"
          icon={<IconShieldLock className="h-[18px] w-[18px]" />}
          title={pending ? "Phê duyệt tài khoản" : "Phân quyền tài khoản"}
          description={`${user.name || user.username} · ${user.username}`}
          onClose={onClose}
        />
        <DialogBody className="space-y-4">
          {error && <Notice tone="danger">{error}</Notice>}
          <Field label="Vai trò" htmlFor="approve-role">
            <Select id="approve-role" value={role} onChange={(e) => setRole(e.target.value)} data-autofocus>
              <option value="qlv">{ROLE_LABELS.qlv}</option>
              <option value="regional_director">{ROLE_LABELS.regional_director}</option>
              <option value="c_level">{ROLE_LABELS.c_level}</option>
              <option value="admin_ops">{ROLE_LABELS.admin_ops}</option>
            </Select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Phụ trách vùng" htmlFor="approve-region">
              <Select id="approve-region" value={scopeValue} onChange={(e) => setScopeValue(e.target.value)} disabled={scopeLocked}>
                <option value="">Tất cả / không</option>
                {REGION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
            <Field label="Phụ trách kênh" htmlFor="approve-channel">
              <Select id="approve-channel" value={scopeChannel} onChange={(e) => setScopeChannel(e.target.value)} disabled={scopeLocked}>
                <option value="">Tất cả / không</option>
                {CHANNEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
          </div>
          {scopeLocked && <p className="text-[12.5px] text-slate-500">Vai trò này xem được toàn công ty nên không cần chọn vùng, kênh.</p>}
          {role === "qlv" && (
            <Field label="Mã nhân viên Bravo" htmlFor="approve-emp" hint="Mã QLV trên Bravo, ví dụ MBKV1 — dùng để giới hạn số liệu theo đội.">
              <TextInput id="approve-emp" placeholder="MBKV1" value={employeeCode} onChange={(e) => setEmployeeCode(e.target.value)} />
            </Field>
          )}
          <Field label="Email công ty" htmlFor="approve-email" hint="Nơi nhận mật khẩu khi được cấp lại. Để trống là giữ nguyên email hiện có.">
            <TextInput id="approve-email" type="email" placeholder="ten.ho@namhapharma.com" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>Hủy</Button>
          <Button type="submit" variant="primary" loading={saving}>{pending ? "Phê duyệt" : "Lưu phân quyền"}</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function CreateUserDialog({ open, authToken, onClose, onCreated }: {
  open: boolean;
  authToken: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("qlv");
  const [scopeValue, setScopeValue] = useState("");
  const [employeeCode, setEmployeeCode] = useState("");
  const [scopeChannel, setScopeChannel] = useState("");
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ text: string; type: "success" | "warning" | "error"; pwd?: string } | null>(null);
  const [copied, setCopied] = useState(false);

  function close() {
    setResult(null);
    setCopied(false);
    onClose();
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setResult(null);
    setCopied(false);
    try {
      const res = await fetch("/api/admin/users/create", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
        body: JSON.stringify({
          username: username.trim(),
          password: password.trim() || null,
          email: email.trim() || null,
          name: name.trim() || null,
          role,
          scope_value: role === "c_level" ? null : (scopeValue || null),
          employee_code: role === "qlv" ? (employeeCode.trim() || null) : null,
          scope_channel: scopeChannel || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Tạo tài khoản thất bại");
      setResult(data.email_sent === false
        ? { text: "Đã tạo tài khoản nhưng KHÔNG gửi được email. Hãy chép mật khẩu bên dưới và gửi trực tiếp cho người dùng.", type: "warning", pwd: data.generated_password }
        : { text: data.message || "Tạo tài khoản thành công.", type: "success", pwd: data.generated_password });
      setUsername("");
      setPassword("");
      setEmail("");
      setName("");
      setEmployeeCode("");
      setScopeValue("");
      setScopeChannel("");
      onCreated();
    } catch (err) {
      setResult({ text: errorMessage(err, "Tạo tài khoản thất bại"), type: "error" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={close} labelledBy="create-user-title" size="lg" closeOnBackdrop={false}>
      <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
        <DialogHeader
          id="create-user-title"
          icon={<IconUserPlus className="h-[18px] w-[18px]" />}
          title="Tạo tài khoản mới"
          description="Mật khẩu được gửi tự động tới email Outlook của nhân viên."
          onClose={close}
        />
        <DialogBody className="space-y-4">
          {result && (
            <Notice tone={result.type === "error" ? "danger" : result.type}>
              {result.text}
              {result.pwd && (
                <div className="mt-2.5 flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2 ring-1 ring-inset ring-line">
                  <span className="text-[13px]">Mật khẩu vừa sinh: <span className="select-all font-mono font-semibold text-navy">{result.pwd}</span></span>
                  <Button size="sm" variant="ghost" icon={<IconCopy className="h-3.5 w-3.5" />}
                    onClick={() => navigator.clipboard?.writeText(result.pwd || "").then(() => setCopied(true)).catch(() => {})}>
                    {copied ? "Đã sao chép" : "Sao chép"}
                  </Button>
                </div>
              )}
            </Notice>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tên đăng nhập" htmlFor="new-username">
              <TextInput id="new-username" required placeholder="vui.hoangthi" value={username} onChange={(e) => setUsername(e.target.value)} data-autofocus autoComplete="off" />
            </Field>
            <Field label="Mật khẩu" htmlFor="new-password" hint="Để trống để hệ thống tự sinh.">
              <TextInput id="new-password" type="text" placeholder="Tự sinh" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
            </Field>
            <Field label="Họ và tên" htmlFor="new-name">
              <TextInput id="new-name" placeholder="Hoàng Thị Vui" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Email nhận mật khẩu" htmlFor="new-email">
              <TextInput id="new-email" type="email" placeholder="vui.hoangthi@namhapharma.com" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
          </div>
          <div className="h-px bg-line" />
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Vai trò" htmlFor="new-role">
              <Select id="new-role" value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="qlv">{ROLE_LABELS.qlv}</option>
                <option value="regional_director">{ROLE_LABELS.regional_director}</option>
                <option value="c_level">{ROLE_LABELS.c_level}</option>
                <option value="admin_ops">{ROLE_LABELS.admin_ops}</option>
              </Select>
            </Field>
            <Field label="Phụ trách vùng" htmlFor="new-region">
              <Select id="new-region" value={scopeValue} onChange={(e) => setScopeValue(e.target.value)} disabled={role === "c_level"}>
                <option value="">Tất cả / không</option>
                {REGION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
            <Field label="Phụ trách kênh" htmlFor="new-channel">
              <Select id="new-channel" value={scopeChannel} onChange={(e) => setScopeChannel(e.target.value)}>
                <option value="">Tất cả / không</option>
                {CHANNEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
          </div>
          {role === "qlv" && (
            <Field label="Mã nhân viên Bravo" htmlFor="new-emp" hint="Mã QLV trên Bravo, ví dụ MBKV1 — dùng để giới hạn số liệu theo đội.">
              <TextInput id="new-emp" placeholder="MBKV1" value={employeeCode} onChange={(e) => setEmployeeCode(e.target.value)} />
            </Field>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={close}>Đóng</Button>
          <Button type="submit" variant="primary" loading={saving}>Tạo tài khoản & gửi email</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
