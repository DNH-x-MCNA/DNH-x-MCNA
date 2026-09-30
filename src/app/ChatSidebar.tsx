"use client";

import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  IconChart, IconClose, IconCompose, IconKey, IconLogout, IconSearch, IconSelector, IconSidebar, IconTrash, IconUsers,
} from "./icons";
import {
  SessionSummary, UserInfo, displayName, foldVietnamese, formatRelativeTime, groupSessionsByDate, roleLabel,
  scopeLabel,
} from "./lib";
import { Avatar, IconButton, Select, Skeleton, cx } from "./ui";

type Owner = { username: string; label: string; count: number };

export function ChatSidebar({
  open, onClose, collapsed, onCollapse, user, isAdmin, sessions, sessionsLoaded, currentSessionId, busy,
  onSelect, onNew, onRequestDelete, onOpenAudit, onOpenUsers, onChangePassword, onLogout,
}: {
  open: boolean;
  onClose: () => void;
  /** May tinh: nguoi dung da thu gon thanh ben. Man hinh nho van dong/mo bang `open` nhu cu. */
  collapsed: boolean;
  onCollapse: () => void;
  user: UserInfo;
  isAdmin: boolean;
  sessions: SessionSummary[];
  sessionsLoaded: boolean;
  currentSessionId: string;
  busy: boolean;
  onSelect: (sid: string) => void;
  onNew: () => void;
  onRequestDelete: (session: SessionSummary) => void;
  onOpenAudit: () => void;
  onOpenUsers: () => void;
  onChangePassword: () => void;
  onLogout: () => void;
}) {
  const [query, setQuery] = useState("");

  // Man hinh nho: Esc dong thanh ben dang mo (tren may tinh thu gon bang nut, khong can).
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  // Loc lich su tro chuyen theo nguoi dung. Chi C-Level/GD mien moi thay nhieu chu so huu trong
  // `sessions` (backend loc), tai khoan thuong luon chi co dung 1 chu so huu la chinh minh.
  const [ownerFilter, setOwnerFilter] = useState("all");

  // Danh sach chu so huu kem so cuoc tro chuyen - dung dung nguon `sessions` dang hien thi nen con so
  // trong bo loc luon khop voi so dong ben duoi. Minh luon dung dau danh sach.
  const me = user.username;
  const owners = useMemo<Owner[]>(() => {
    const byUser = new Map<string, Owner>();
    for (const s of sessions) {
      const existing = byUser.get(s.owner_username);
      if (existing) existing.count += 1;
      else byUser.set(s.owner_username, { username: s.owner_username, label: s.owner_name || s.owner_username, count: 1 });
    }
    return Array.from(byUser.values()).sort((a, b) => {
      if (a.username === me) return -1;
      if (b.username === me) return 1;
      return a.label.localeCompare(b.label, "vi");
    });
  }, [sessions, me]);

  // Nguoi dang duoc loc khong con cuoc tro chuyen nao (vd vua xoa het) -> coi nhu "tat ca".
  const effectiveOwner = ownerFilter !== "all" && !owners.some((o) => o.username === ownerFilter) ? "all" : ownerFilter;
  const showOwnerFilter = (isAdmin || user.role === "regional_director") && owners.length > 1;

  const visible = useMemo(() => {
    const q = foldVietnamese(query.trim());
    return sessions.filter((s) => {
      if (effectiveOwner !== "all" && s.owner_username !== effectiveOwner) return false;
      if (!q) return true;
      return foldVietnamese(`${s.title || ""} ${s.owner_name || ""}`).includes(q);
    });
  }, [sessions, effectiveOwner, query]);
  const groups = groupSessionsByDate(visible);

  return (
    <>
      {open && <div className="fixed inset-0 z-30 animate-fade-in bg-slate-950/30 md:hidden" onClick={onClose} aria-hidden="true" />}
      {/* Thanh ben navy - giu mau thanh dieu huong toi cua ban 29/07, tach ro vung lich su voi vung doc
          cau tra loi (nen trang). */}
      <aside
        aria-label="Lịch sử trò chuyện"
        className={cx(
          "z-40 w-[288px] shrink-0 flex-col bg-navy text-slate-300 [&_:focus-visible]:outline-indigo-300",
          open ? "fixed inset-y-0 left-0 flex animate-sheet-in shadow-float" : "hidden",
          "md:static md:animate-none md:shadow-none",
          collapsed ? "md:hidden" : "md:flex",
        )}
      >
        <div className="flex h-14 items-center gap-2.5 px-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/namha-mark.png" alt="" aria-hidden="true" className="h-7 w-7" />
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-[14px] font-semibold tracking-tight text-white">DNH AI Analyst</div>
            <div className="text-[12px] text-slate-400">Dược Nam Hà</div>
          </div>
          {/* max-md:hidden thay vi "hidden md:inline-flex": IconButton da co san inline-flex. */}
          <IconButton label="Thu gọn thanh bên" tone="inverse" onClick={onCollapse} className="max-md:hidden">
            <IconSidebar className="h-5 w-5" />
          </IconButton>
          <IconButton label="Đóng thanh bên" tone="inverse" onClick={onClose} className="md:hidden">
            <IconClose className="h-5 w-5" />
          </IconButton>
        </div>

        <div className="space-y-2 px-3 pb-2 pt-1">
          <button
            type="button"
            onClick={onNew}
            disabled={busy}
            className="flex h-10 w-full items-center gap-2.5 rounded-xl bg-brand px-3 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconCompose className="h-[18px] w-[18px]" />
            Cuộc trò chuyện mới
          </button>
          {sessions.length > 0 && (
            <div className="relative">
              <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Tìm cuộc trò chuyện"
                aria-label="Tìm cuộc trò chuyện"
                className="h-9 w-full rounded-lg bg-white/[0.07] pl-9 pr-3 text-[13.5px] text-white outline-none ring-1 ring-inset ring-white/10 transition placeholder:text-slate-400 hover:ring-white/20 focus:bg-white/10 focus:ring-2 focus:ring-indigo-300"
              />
            </div>
          )}
          {showOwnerFilter && (
            <Select inverse value={effectiveOwner} onChange={(e) => setOwnerFilter(e.target.value)} aria-label="Lọc theo người dùng">
              <option value="all">Tất cả người dùng ({sessions.length})</option>
              {owners.map((o) => (
                <option key={o.username} value={o.username}>
                  {o.username === user.username ? `${o.label} (bạn)` : o.label} · {o.count}
                </option>
              ))}
            </Select>
          )}
        </div>

        <nav className="custom-scroll scroll-on-dark min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {!sessionsLoaded ? (
            <div className="space-y-3 px-2 pt-3">
              {[72, 56, 64, 48].map((w) => (
                <div key={w} className="space-y-1.5" style={{ width: `${w + 20}%` }}>
                  <Skeleton inverse className="h-3.5" />
                  <Skeleton inverse className="h-2.5" />
                </div>
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p className="px-3 pt-4 text-[13px] leading-relaxed text-slate-400">
              Các cuộc trò chuyện của bạn sẽ hiện ở đây.
            </p>
          ) : visible.length === 0 ? (
            <p className="px-3 pt-4 text-[13px] text-slate-400">Không tìm thấy cuộc trò chuyện phù hợp.</p>
          ) : (
            groups.map((group) => (
              <div key={group.label} className="pt-3">
                <div className="px-2.5 pb-1 text-[12px] font-semibold text-slate-400">{group.label}</div>
                <ul className="space-y-0.5">
                  {group.items.map((s) => {
                    const active = s.session_id === currentSessionId;
                    const own = s.owner_username === user.username;
                    return (
                      <li key={s.session_id} className="group relative">
                        <button
                          type="button"
                          onClick={() => onSelect(s.session_id)}
                          aria-current={active ? "true" : undefined}
                          // Dang nhan cau tra loi thi khong chuyen cuoc: stream dang do se ghi lan sang cuoc moi.
                          disabled={busy && !active}
                          title={busy && !active ? "Đợi câu trả lời hiện tại xong rồi chuyển" : undefined}
                          className={cx(
                            "w-full rounded-xl px-2.5 py-2 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
                            own && "pr-10",
                            active ? "bg-white/[0.12] ring-1 ring-inset ring-white/10" : "hover:bg-white/[0.06] disabled:hover:bg-transparent",
                          )}
                        >
                          <span className={cx("fade-truncate block text-[13.5px]", active ? "font-medium text-white" : "text-slate-200")}>
                            {s.title || "Cuộc trò chuyện mới"}
                          </span>
                          <span className="fade-truncate block text-[12px] text-slate-400">
                            {formatRelativeTime(s.updated_at)}
                            {!own ? ` · ${s.owner_name || s.owner_username}` : ""}
                          </span>
                        </button>
                        {own && (
                          <IconButton
                            label="Xóa cuộc trò chuyện"
                            size="sm"
                            tone="inverseDanger"
                            disabled={busy}
                            onClick={() => onRequestDelete(s)}
                            className="absolute right-1.5 top-1/2 -translate-y-1/2 opacity-100 focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100"
                          >
                            <IconTrash className="h-4 w-4" />
                          </IconButton>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}
        </nav>

        <div className="border-t border-white/10 p-2">
          {isAdmin && (
            <div className="mb-1 space-y-0.5">
              <SidebarAction icon={<IconChart className="h-[18px] w-[18px]" />} label="Chi phí AI & nhật ký" onClick={onOpenAudit} />
              <SidebarAction icon={<IconUsers className="h-[18px] w-[18px]" />} label="Tài khoản nhân viên" onClick={onOpenUsers} />
            </div>
          )}
          <AccountMenu user={user} onChangePassword={onChangePassword} onLogout={onLogout} />
        </div>
      </aside>
    </>
  );
}

function SidebarAction({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] text-slate-200 transition hover:bg-white/[0.06] hover:text-white"
    >
      <span className="text-slate-400">{icon}</span>
      {label}
    </button>
  );
}

function AccountMenu({ user, onChangePassword, onLogout }: {
  user: UserInfo;
  onChangePassword: () => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = displayName(user);
  const limit = user.quota_limit;
  return (
    <div ref={rootRef} className="relative">
      {open && (
        <div role="menu" className="absolute bottom-full left-0 right-0 mb-2 animate-rise-in overflow-hidden rounded-2xl bg-white p-1.5 shadow-float ring-1 ring-slate-900/5">
          <div className="px-3 pb-2.5 pt-2">
            <div className="truncate text-[14px] font-medium text-navy">{name}</div>
            {user.email && <div className="truncate text-[12.5px] text-slate-600">{user.email}</div>}
            <div className="mt-2 space-y-0.5 text-[12.5px] text-slate-600">
              <div>{roleLabel(user.role)}</div>
              {user.role !== "admin_ops" && <div>Phạm vi: {scopeLabel(user)}</div>}
              {limit != null && (
                <div>
                  Còn <span className="font-medium tabular-nums text-slate-900">{user.quota_remaining}/{limit}</span> câu tuần này
                  {user.quota_resets_at && ` · làm mới ${new Date(user.quota_resets_at).toLocaleString("vi-VN", { weekday: "short", hour: "2-digit", minute: "2-digit" })}`}
                </div>
              )}
            </div>
          </div>
          <div className="my-1 h-px bg-line" />
          <MenuItem icon={<IconKey className="h-4 w-4" />} label="Đổi mật khẩu" onClick={() => { setOpen(false); onChangePassword(); }} />
          <MenuItem icon={<IconLogout className="h-4 w-4" />} label="Đăng xuất" onClick={() => { setOpen(false); onLogout(); }} danger />
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cx("flex w-full items-center gap-2.5 rounded-xl p-2 text-left transition hover:bg-white/[0.06]", open && "bg-white/[0.08]")}
      >
        <Avatar name={name} className="h-8 w-8" />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[13.5px] font-medium text-white">{name}</span>
          <span className="block truncate text-[12px] text-slate-400">{roleLabel(user.role)}</span>
        </span>
        <IconSelector className="h-4 w-4 shrink-0 text-slate-500" />
      </button>
    </div>
  );
}

function MenuItem({ icon, label, onClick, danger = false }: { icon: ReactNode; label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cx(
        "flex h-9 w-full items-center gap-2.5 rounded-lg px-3 text-[13.5px] transition",
        danger ? "text-red-600 hover:bg-red-50" : "text-slate-800 hover:bg-sunken hover:text-navy",
      )}
    >
      {icon}
      {label}
    </button>
  );
}
