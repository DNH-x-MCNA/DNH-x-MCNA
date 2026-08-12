"use client";

import React, { useState } from "react";
import {
  IconChart,
  IconCheck,
  IconClock,
  IconKey,
  IconLightbulb,
  IconShieldLock,
  IconUnlock,
  IconWarning,
} from "./icons";

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
    <div className="auth-shell relative min-h-screen overflow-hidden bg-[#071426] px-4 py-6 text-slate-900 sm:px-6 lg:px-10 lg:py-10">
      <div className="pointer-events-none absolute -left-32 -top-40 h-[32rem] w-[32rem] rounded-full bg-blue-600/25 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-48 -right-20 h-[34rem] w-[34rem] rounded-full bg-teal-400/10 blur-3xl" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.06] [background-image:linear-gradient(rgba(255,255,255,.8)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.8)_1px,transparent_1px)] [background-size:42px_42px]" />

      <div className="relative mx-auto grid min-h-[calc(100vh-3rem)] w-full max-w-6xl overflow-hidden rounded-[2rem] border border-white/10 bg-white/5 shadow-2xl shadow-black/30 backdrop-blur-sm lg:min-h-[calc(100vh-5rem)] lg:grid-cols-[1.05fr_0.95fr]">
        <section className="relative hidden flex-col justify-between overflow-hidden p-10 text-white lg:flex xl:p-14">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_10%,rgba(37,99,235,.34),transparent_42%),linear-gradient(145deg,rgba(15,39,72,.92),rgba(7,20,38,.98))]" />
          <div className="relative">
            <div className="mb-16 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white p-1.5 shadow-lg shadow-blue-950/30">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/namha-logo.png" alt="Nam Hà Pharma" className="h-full w-full object-contain" />
              </div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-teal-300">Nam Hà Pharma</div>
                <div className="mt-0.5 text-sm font-semibold text-white/90">Decision Intelligence</div>
              </div>
            </div>

            <div className="max-w-xl">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-teal-300/25 bg-teal-300/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-teal-200">
                <span className="h-1.5 w-1.5 rounded-full bg-teal-300 shadow-[0_0_0_4px_rgba(94,234,212,.12)]" />
                Trợ lý dữ liệu nội bộ
              </div>
              <h2 className="max-w-lg text-4xl font-semibold leading-[1.08] tracking-[-0.04em] xl:text-5xl">
                Biến dữ liệu kinh doanh thành quyết định rõ ràng.
              </h2>
              <p className="mt-6 max-w-lg text-base leading-7 text-slate-300">
                Hỏi về doanh thu, công nợ, KPI và hiệu quả vận hành bằng ngôn ngữ tự nhiên. DNH AI Analyst giúp đội ngũ điều hành nhìn thấy tín hiệu quan trọng nhanh hơn.
              </p>
            </div>

            <div className="mt-12 grid max-w-xl grid-cols-3 gap-3">
              {[
                { value: "24/7", label: "Sẵn sàng" },
                { value: "Realtime", label: "Dữ liệu cập nhật" },
                { value: "RBAC", label: "Phân quyền" },
              ].map((stat) => (
                <div key={stat.label} className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm">
                  <div className="text-lg font-semibold tracking-tight text-white">{stat.value}</div>
                  <div className="mt-1 text-[11px] text-slate-400">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative flex items-center gap-3 text-xs text-slate-400">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-teal-300"><IconShieldLock className="h-4 w-4" /></div>
            <span>Dữ liệu được bảo vệ theo vai trò và phạm vi truy cập của từng tài khoản.</span>
          </div>
        </section>

        <section className="flex items-center justify-center bg-[#f8fafc] p-4 sm:p-8 lg:p-10">
          <div className="w-full max-w-md">
            <div className="mb-8 flex items-center justify-between lg:hidden">
              <div className="flex items-center gap-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white p-1 shadow-sm ring-1 ring-slate-200">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/namha-logo.png" alt="Nam Hà Pharma" className="h-full w-full object-contain" />
                </div>
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-blue-700">Nam Hà Pharma</div>
                  <div className="text-xs font-semibold text-slate-700">Decision Intelligence</div>
                </div>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Online
              </span>
            </div>

            <div className="mb-7">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">DNH AI Analyst</span>
                <span className="hidden items-center gap-1.5 text-[10px] font-medium text-slate-400 sm:inline-flex"><IconClock className="h-3.5 w-3.5" /> Truy cập bảo mật</span>
              </div>
              <h1 className="text-3xl font-semibold tracking-[-0.04em] text-slate-950">Chào mừng trở lại.</h1>
              <p className="mt-2 text-sm leading-6 text-slate-500">Đăng nhập để tiếp tục phiên phân tích và theo dõi những chỉ số quan trọng của bạn.</p>
            </div>

            <div className="overflow-hidden rounded-[1.5rem] border border-slate-200 bg-white shadow-xl shadow-slate-900/5">
              <div className="flex border-b border-slate-200 bg-slate-50/80">
                <button
                  onClick={() => { setTab("login"); setMessage(null); }}
                  className={`flex-1 py-4 text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${tab === "login" ? "bg-white text-blue-700 shadow-[inset_0_-2px_0_#2563eb]" : "text-slate-500 hover:text-blue-600"}`}
                >
                  <IconKey className="w-3.5 h-3.5" /> Đăng nhập hệ thống
                </button>
                <button
                  onClick={() => { setTab("forgot"); setMessage(null); }}
                  className={`flex-1 py-4 text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${tab === "forgot" ? "bg-white text-amber-700 shadow-[inset_0_-2px_0_#d97706]" : "text-slate-500 hover:text-amber-600"}`}
                >
                  <IconUnlock className="w-3.5 h-3.5" /> Quên mật khẩu
                </button>
              </div>

              <div className="p-5 sm:p-7">
                {message && (
                  <div className={`mb-4 flex items-start gap-2 rounded-xl border p-3.5 text-xs font-medium ${message.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
                    <span>{message.type === "success" ? <IconCheck className="h-4 w-4" /> : <IconWarning className="h-4 w-4" />}</span>
                    <span className="flex-1">{message.text}</span>
                  </div>
                )}

                {tab === "login" && (
                  <form onSubmit={handleLoginSubmit} className="space-y-4">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold text-slate-700">Email công ty hoặc Tên đăng nhập</label>
                      <input type="text" required placeholder="nhanvien@namhapharma.com hoặc username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm text-slate-800 transition placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-blue-500/10" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold text-slate-700">Mật khẩu</label>
                      <input type="password" required placeholder="Nhập mật khẩu" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm text-slate-800 transition placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-blue-500/10" />
                    </div>
                    <div className="flex items-start gap-2 rounded-xl border border-blue-100 bg-blue-50/70 p-3.5 text-[11px] leading-5 text-slate-600">
                      <IconLightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600" />
                      <span><strong>Lưu ý:</strong> Tài khoản mới do Quản trị viên (C-Level) khởi tạo. Mật khẩu khởi tạo được gửi trực tiếp về email Outlook của nhân viên.</span>
                    </div>
                    <button type="submit" disabled={loading} className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-700 via-blue-700 to-indigo-700 py-3.5 text-sm font-semibold text-white shadow-lg shadow-blue-700/20 transition hover:-translate-y-0.5 hover:shadow-xl hover:shadow-blue-700/25 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0">
                      {loading ? "Đang xác thực..." : <>Đăng nhập ngay <span className="transition-transform group-hover:translate-x-0.5">→</span></>}
                    </button>
                  </form>
                )}

                {tab === "forgot" && (
                  <form onSubmit={handleForgotSubmit} className="space-y-4">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold text-slate-700">Email Dược Nam Hà (@namhapharma.com)</label>
                      <input type="email" required placeholder="tennhanvien@namhapharma.com" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm text-slate-800 transition placeholder:text-slate-400 focus:border-amber-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-amber-500/10" />
                    </div>
                    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs leading-5 text-amber-900">Mật khẩu mới sẽ được sinh tự động và gửi về email Outlook. Tất cả các phiên làm việc trước đó trên các thiết bị khác sẽ tự động bị đăng xuất.</div>
                    <button type="submit" disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 py-3.5 text-sm font-semibold text-white shadow-lg shadow-amber-700/20 transition hover:-translate-y-0.5 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0">
                      {loading ? "Đang xử lý..." : <>Cấp lại mật khẩu mới qua Email <IconUnlock className="h-4 w-4" /></>}
                    </button>
                  </form>
                )}
              </div>
            </div>
            <div className="mt-5 flex items-center justify-center gap-2 text-[10px] font-medium text-slate-400"><IconChart className="h-3.5 w-3.5" /> Hệ thống báo cáo quản trị nội bộ · Nam Hà Pharma</div>
          </div>
        </section>
      </div>
    </div>
  );
}
