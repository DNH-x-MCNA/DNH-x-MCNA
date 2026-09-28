"use client";

import { FormEvent, useState } from "react";
import { IconKey } from "./icons";
import { authHeaders } from "./lib";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, Notice, PasswordInput } from "./ui";

export function ChangePasswordDialog({ open, authToken, onClose }: {
  open: boolean;
  authToken: string | null;
  onClose: () => void;
}) {
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function close() {
    setMessage(null);
    setCurrentPwd("");
    setNewPwd("");
    onClose();
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: authHeaders(authToken),
        body: JSON.stringify({ current_password: currentPwd, new_password: newPwd }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Đổi mật khẩu thất bại");
      setMessage({ text: data.message || "Đổi mật khẩu thành công.", type: "success" });
      setCurrentPwd("");
      setNewPwd("");
    } catch (err) {
      setMessage({ text: (err as Error).message, type: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={close} labelledBy="change-pwd-title" size="md" closeOnBackdrop={false}>
      <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
        <DialogHeader
          id="change-pwd-title"
          icon={<IconKey className="h-[18px] w-[18px]" />}
          title="Đổi mật khẩu"
          description="Sau khi đổi, các phiên đăng nhập trên thiết bị khác sẽ bị đăng xuất."
          onClose={close}
        />
        <DialogBody className="space-y-4">
          {message && <Notice tone={message.type === "success" ? "success" : "danger"}>{message.text}</Notice>}
          <Field label="Mật khẩu hiện tại" htmlFor="pwd-current">
            <PasswordInput id="pwd-current" required autoComplete="current-password" value={currentPwd}
              onChange={(e) => setCurrentPwd(e.target.value)} data-autofocus />
          </Field>
          <Field label="Mật khẩu mới" htmlFor="pwd-new" hint="Tối thiểu 6 ký tự.">
            <PasswordInput id="pwd-new" required minLength={6} autoComplete="new-password" value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)} />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={close}>{message?.type === "success" ? "Xong" : "Hủy"}</Button>
          <Button type="submit" variant="primary" loading={submitting}>Cập nhật mật khẩu</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
