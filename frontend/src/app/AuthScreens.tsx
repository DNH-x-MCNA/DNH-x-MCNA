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
    <div className="flex min-h-dvh flex-col bg-soft">
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-[400px] animate-rise-in">
          <div className="mb-8 flex flex-col items-center text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/namha-logo.png" alt="Công ty Cổ phần Dược Nam Hà" className="h-12 w-auto" />
            <h1 className="mt-7 text-[24px] font-semibold tracking-tight text-navy">
              {view === "login" ? "Đăng nhập" : "Lấy lại mật khẩu"}
            </h1>
            <p className="mt-1.5 max-w-sm text-[14.5px] leading-relaxed text-slate-500">
              {view === "login"
                ? "DNH AI Analyst · Trợ lý phân tích kinh doanh"
                : "Nhập email công ty. Mật khẩu mới sẽ được gửi vào hộp thư Outlook của bạn."}
            </p>
          </div>

          <div className="rounded-3xl bg-white p-6 shadow-raised ring-1 ring-slate-900/5 sm:p-7">
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
                  className="mx-auto flex items-center gap-1 text-[13.5px] font-medium text-slate-500 hover:text-navy"
                >
                  <IconChevronLeft className="h-4 w-4" /> Quay lại đăng nhập
                </button>
              </form>
            )}
          </div>

          <p className="mt-6 text-center text-[13px] leading-relaxed text-slate-400">
            Tài khoản do quản trị viên cấp. Mật khẩu khởi tạo được gửi qua email Outlook của nhân viên.
          </p>
        </div>
      </main>
      <footer className="pb-6 text-center text-[12px] text-slate-400">© {new Date().getFullYear()} Công ty Cổ phần Dược Nam Hà</footer>
    </div>
  );
}
