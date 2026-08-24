"use client";

import React, { useState } from "react";
import { IconChart, IconCheck, IconKey, IconLightbulb, IconLock, IconUnlock, IconWarning } from "./icons";

interface AuthScreensProps {
  onLoginSuccess: (token: string, user: AuthUser) => void;
}

type AuthUser = {
  token: string;
  username: string;
  name: string | null;
  role: string;
  scope_value: string | null;
  scope_channel?: string | null;
  status?: string;
  email?: string | null;
  quota_used?: number | null;
  quota_limit?: number | null;
  quota_remaining?: number | null;
  quota_resets_at?: string | null;
};

export default function AuthScreens({ onLoginSuccess }: AuthScreensProps) {
  const [tab, setTab] = useState<"login" | "forgot">("login");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: identifier, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Đăng nhập thất bại");
      onLoginSuccess(data.token, data);
    } catch (err: unknown) {
      setMessage({ text: err instanceof Error ? err.message : "Đăng nhập thất bại", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleForgotSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Yêu cầu cấp lại mật khẩu thất bại");
      setMessage({ text: data.message, type: "success" });
    } catch (err: unknown) {
      setMessage({ text: err instanceof Error ? err.message : "Yêu cầu cấp lại mật khẩu thất bại", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f5f8f5] px-4 py-8 text-slate-900 sm:px-6">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-between px-1">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white p-1.5 shadow-sm ring-1 ring-emerald-100">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/namha-logo.png" alt="Nam Hà Pharma" className="h-full w-full object-contain" />
            </div>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-700">Nam Hà Pharma</div>
              <div className="mt-0.5 text-xs text-slate-500">DNH AI Analyst</div>
            </div>
          </div>
          <div className="inline-flex items-center gap-1.5 text-[10px] font-medium text-slate-500">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Hệ thống hoạt động
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-emerald-100 bg-white shadow-xl shadow-emerald-950/5">
          <div className="h-1 bg-gradient-to-r from-emerald-800 via-emerald-600 to-orange-400" />
          <div className="border-b border-slate-200 px-6 py-6 sm:px-8">
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-800 text-white shadow-sm shadow-emerald-900/15">
              {tab === "login" ? <IconLock className="h-5 w-5" /> : <IconUnlock className="h-5 w-5" />}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-950">{tab === "login" ? "Đăng nhập" : "Cấp lại mật khẩu"}</h1>
            <p className="mt-1.5 text-sm leading-6 text-slate-500">
              {tab === "login" ? "Truy cập trợ lý phân tích dữ liệu kinh doanh nội bộ." : "Nhập email công ty để nhận mật khẩu mới."}
            </p>
          </div>

          <div className="flex border-b border-slate-200 bg-[#f8fbf8]">
            <button
              onClick={() => { setTab("login"); setMessage(null); }}
              className={`flex-1 border-b-2 py-3.5 text-xs font-semibold transition ${tab === "login" ? "border-emerald-700 bg-white text-emerald-800" : "border-transparent text-slate-500 hover:text-emerald-800"}`}
            >
              <span className="inline-flex items-center gap-1.5"><IconKey className="h-3.5 w-3.5" /> Đăng nhập</span>
            </button>
            <button
              onClick={() => { setTab("forgot"); setMessage(null); }}
              className={`flex-1 border-b-2 py-3.5 text-xs font-semibold transition ${tab === "forgot" ? "border-emerald-700 bg-white text-emerald-800" : "border-transparent text-slate-500 hover:text-emerald-800"}`}
            >
              <span className="inline-flex items-center gap-1.5"><IconUnlock className="h-3.5 w-3.5" /> Quên mật khẩu</span>
            </button>
          </div>

          <div className="p-6 sm:p-8">
            {message && (
              <div className={`mb-5 flex items-start gap-2 rounded-xl border p-3.5 text-xs font-medium ${message.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
                {message.type === "success" ? <IconCheck className="h-4 w-4 shrink-0" /> : <IconWarning className="h-4 w-4 shrink-0" />}
                <span>{message.text}</span>
              </div>
            )}

            {tab === "login" ? (
              <form onSubmit={handleLoginSubmit} className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-slate-700">Email công ty hoặc tên đăng nhập</label>
                  <input type="text" required placeholder="nhanvien@namhapharma.com hoặc username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-slate-900 focus:ring-4 focus:ring-slate-900/10" />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-slate-700">Mật khẩu</label>
                  <input type="password" required placeholder="Nhập mật khẩu" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-slate-900 focus:ring-4 focus:ring-slate-900/10" />
                </div>
                <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-[11px] leading-5 text-slate-600">
                  <IconLightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                  <span><strong>Lưu ý:</strong> Tài khoản mới do Quản trị viên khởi tạo. Mật khẩu khởi tạo được gửi trực tiếp về email Outlook.</span>
                </div>
                <button type="submit" disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50">
                  {loading ? "Đang xác thực..." : <>Đăng nhập <span>→</span></>}
                </button>
              </form>
            ) : (
              <form onSubmit={handleForgotSubmit} className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-slate-700">Email Dược Nam Hà</label>
                  <input type="email" required placeholder="tennhanvien@namhapharma.com" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-slate-900 focus:ring-4 focus:ring-slate-900/10" />
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs leading-5 text-slate-600">Mật khẩu mới sẽ được sinh tự động và gửi về email Outlook. Các phiên cũ sẽ tự động bị đăng xuất.</div>
                <button type="submit" disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50">
                  {loading ? "Đang xử lý..." : <>Gửi mật khẩu mới <IconUnlock className="h-4 w-4" /></>}
                </button>
              </form>
            )}
          </div>
        </div>

        <div className="mt-5 flex items-center justify-center gap-2 text-[10px] font-medium text-slate-400"><IconChart className="h-3.5 w-3.5" /> Hệ thống báo cáo quản trị nội bộ</div>
      </div>
    </div>
  );
}
