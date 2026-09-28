"use client";

import { FormEvent, useState } from "react";
import { IconChevronLeft } from "./icons";
import type { UserInfo } from "./lib";
import { Button, Field, Notice, PasswordInput, TextInput } from "./ui";

interface AuthScreensProps {
  onLoginSuccess: (token: string, user: UserInfo) => void;
}

export default function AuthScreens({ onLoginSuccess }: AuthScreensProps) {
  // Khong co tu dang ky: tai khoan do quan tri vien (C-Level) khoi tao.
  const [view, setView] = useState<"login" | "forgot">("login");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  function switchView(next: "login" | "forgot") {
    setView(next);
    setMessage(null);
  }

  const handleLoginSubmit = async (e: FormEvent) => {
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
    } catch (err) {
      setMessage({ text: (err as Error).message, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleForgotSubmit = async (e: FormEvent) => {
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
    } catch (err) {
      setMessage({ text: (err as Error).message, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    // Nen navy (mau thanh dieu huong toi cua ban 29/07) + the trang: form noi ro tren nen, khong con
    // trang tren trang. Logo nam trong the vi chu "NAMHA" mau xanh dam khong doc duoc tren navy.
    <div className="relative flex min-h-dvh flex-col overflow-hidden bg-navy">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(56rem_32rem_at_50%_-8%,rgb(79_70_229/0.38),transparent_70%)]"
      />
      <main className="relative flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-[420px] animate-rise-in">
          <div className="overflow-hidden rounded-3xl bg-white shadow-float">
            {/* Dai mau thuong hieu Nam Ha (xanh la -> cam) giu tu ban dang nhap truoc. */}
            <div className="h-1 bg-gradient-to-r from-emerald-800 via-emerald-600 to-orange-400" aria-hidden="true" />
            <div className="px-6 pb-7 pt-8 sm:px-8">
            <div className="mb-7 flex flex-col items-center text-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/namha-logo.png" alt="Công ty Cổ phần Dược Nam Hà" className="h-12 w-auto" />
              <h1 className="mt-6 text-[22px] font-semibold tracking-tight text-navy">
                {view === "login" ? "Đăng nhập" : "Lấy lại mật khẩu"}
              </h1>
              <p className="mt-1 max-w-sm text-[14px] leading-relaxed text-slate-600">
                {view === "login"
                  ? "DNH AI Analyst · Trợ lý phân tích kinh doanh"
                  : "Nhập email công ty. Mật khẩu mới sẽ được gửi vào hộp thư Outlook của bạn."}
              </p>
            </div>
            {message && (
              <Notice tone={message.type === "success" ? "success" : "danger"} className="mb-5">{message.text}</Notice>
            )}

            {view === "login" ? (
              <form onSubmit={handleLoginSubmit} className="space-y-4">
                <Field label="Email công ty hoặc tên đăng nhập" htmlFor="login-id">
                  <TextInput
                    id="login-id"
                    required
                    autoFocus
                    autoComplete="username"
                    placeholder="ten.nhanvien@namhapharma.com"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                  />
                </Field>
                <Field
                  label="Mật khẩu"
                  htmlFor="login-pwd"
                  trailing={
                    <button type="button" onClick={() => switchView("forgot")} className="text-[13px] font-medium text-brand hover:text-brand-strong">
                      Quên mật khẩu?
                    </button>
                  }
                >
                  <PasswordInput
                    id="login-pwd"
                    required
                    autoComplete="current-password"
                    placeholder="Nhập mật khẩu"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
                <Button type="submit" variant="primary" size="lg" loading={loading} className="mt-2 w-full">
                  {loading ? "Đang đăng nhập…" : "Đăng nhập"}
                </Button>
              </form>
            ) : (
              <form onSubmit={handleForgotSubmit} className="space-y-4">
                <Field
                  label="Email Dược Nam Hà"
                  htmlFor="forgot-email"
                  hint="Mọi phiên đăng nhập trên thiết bị khác sẽ tự động bị đăng xuất."
                >
                  <TextInput
                    id="forgot-email"
                    type="email"
                    required
                    autoFocus
                    autoComplete="email"
                    placeholder="ten.nhanvien@namhapharma.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </Field>
                <Button type="submit" variant="primary" size="lg" loading={loading} className="mt-2 w-full">
                  {loading ? "Đang gửi…" : "Gửi mật khẩu mới"}
                </Button>
                <button
                  type="button"
                  onClick={() => switchView("login")}
                  className="mx-auto flex items-center gap-1 text-[13.5px] font-medium text-slate-600 hover:text-navy"
                >
                  <IconChevronLeft className="h-4 w-4" /> Quay lại đăng nhập
                </button>
              </form>
            )}
            </div>
          </div>

          <p className="mt-6 text-center text-[13px] leading-relaxed text-slate-300">
            Tài khoản do quản trị viên cấp. Mật khẩu khởi tạo được gửi qua email Outlook của nhân viên.
          </p>
        </div>
      </main>
      <footer className="relative pb-6 text-center text-[12px] text-slate-400">© {new Date().getFullYear()} Công ty Cổ phần Dược Nam Hà</footer>
    </div>
  );
}
