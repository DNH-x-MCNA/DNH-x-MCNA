"use client";

import React, { useState } from "react";

interface AuthScreensProps {
  onLoginSuccess: (token: string, user: any) => void;
}

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
    } catch (err: any) {
      setMessage({ text: err.message, type: "error" });
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
    } catch (err: any) {
      setMessage({ text: err.message, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4 py-8">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-100">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-700 to-emerald-600 p-6 text-white text-center">
          <div className="flex justify-center mb-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/namha-logo.png"
              alt="CÔNG TY CỔ PHẦN DƯỢC NAM HÀ"
              className="h-16 w-auto bg-white/95 p-2 rounded-xl shadow-md border border-white/20 object-contain"
            />
          </div>
          <h1 className="text-xl font-bold tracking-wide uppercase">CÔNG TY CỔ PHẦN DƯỢC NAM HÀ</h1>
          <p className="text-xs text-white/80 mt-1">Hệ thống AI Chatbot Quản trị Báo cáo</p>
        </div>

        {/* Tab Navigation (Bỏ Tự đăng ký, chỉ giữ 2 tab Đăng nhập & Quên mật khẩu) */}
        <div className="flex border-b border-slate-200 bg-slate-50">
          <button
            onClick={() => { setTab("login"); setMessage(null); }}
            className={`flex-1 py-3.5 text-xs font-semibold transition-all ${
              tab === "login"
                ? "bg-white text-blue-700 border-b-2 border-blue-700 shadow-sm"
                : "text-slate-500 hover:text-blue-600"
            }`}
          >
            🔑 1. Đăng nhập hệ thống
          </button>
          <button
            onClick={() => { setTab("forgot"); setMessage(null); }}
            className={`flex-1 py-3.5 text-xs font-semibold transition-all ${
              tab === "forgot"
                ? "bg-white text-amber-700 border-b-2 border-amber-700 shadow-sm"
                : "text-slate-500 hover:text-amber-600"
            }`}
          >
            🔓 2. Quên mật khẩu
          </button>
        </div>

        {/* Form Body */}
        <div className="p-6">
          {message && (
            <div
              className={`p-3.5 rounded-lg text-xs font-medium mb-4 flex items-start gap-2 ${
                message.type === "success"
                  ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                  : "bg-rose-50 text-rose-800 border border-rose-200"
              }`}
            >
              <span>{message.type === "success" ? "✅" : "⚠️"}</span>
              <span className="flex-1">{message.text}</span>
            </div>
          )}

          {/* TAB 1: ĐĂNG NHẬP */}
          {tab === "login" && (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Email công ty hoặc Tên đăng nhập
                </label>
                <input
                  type="text"
                  required
                  placeholder="nhanvien@namhapharma.com hoặc username"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-600 focus:bg-white text-slate-800 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Mật khẩu
                </label>
                <input
                  type="password"
                  required
                  placeholder="Nhập mật khẩu"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-600 focus:bg-white text-slate-800 transition"
                />
              </div>

              <div className="bg-slate-50 border border-slate-200 p-3 rounded text-[11px] text-slate-600">
                💡 <strong>Lưu ý:</strong> Tài khoản mới do Quản trị viên (C-Level) khởi tạo. Mật khẩu khởi tạo được gửi trực tiếp về email Outlook của nhân viên.
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-blue-700 to-blue-800 hover:from-blue-800 hover:to-blue-900 text-white font-semibold text-sm rounded-lg shadow-md transition disabled:opacity-50"
              >
                {loading ? "Đang xác thực..." : "Đăng nhập ngay ➔"}
              </button>
            </form>
          )}

          {/* TAB 2: QUÊN MẬT KHẨU */}
          {tab === "forgot" && (
            <form onSubmit={handleForgotSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Email Dược Nam Hà (@namhapharma.com)
                </label>
                <input
                  type="email"
                  required
                  placeholder="tennhanvien@namhapharma.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-amber-600 focus:bg-white text-slate-800 transition"
                />
              </div>

              <div className="bg-amber-50 border-l-4 border-amber-600 p-3 rounded text-xs text-amber-900">
                Mật khẩu mới sẽ được sinh tự động và gửi về email Outlook. Tất cả các phiên làm việc trước đó trên các thiết bị khác sẽ tự động bị đăng xuất.
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-700 hover:to-amber-800 text-white font-semibold text-sm rounded-lg shadow-md transition disabled:opacity-50"
              >
                {loading ? "Đang xử lý..." : "Cấp lại mật khẩu mới qua Email 🔓"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
