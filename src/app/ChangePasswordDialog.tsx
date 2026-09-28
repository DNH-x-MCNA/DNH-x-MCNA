"use client";

import { FormEvent, useState } from "react";
import { IconKey } from "./icons";
import { authHeaders } from "./lib";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, Notice, PasswordInput } from "./ui";

/** `forced`: dang dung mat khau tam (must_change_password) - khong dong/huy duoc cho toi khi doi xong.
 *  Doi thanh cong -> backend thu hoi moi phien, nen sau 1 giay goi onPasswordChanged de ve man dang nhap. */
export function ChangePasswordDialog({ open, forced, authToken, onClose, onPasswordChanged }: {
  open: boolean;
  forced: boolean;
  authToken: string | null;
  onClose: () => void;
  onPasswordChanged: () => void;
}) {
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function close() {
    if (forced) return;
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
      window.setTimeout(() => {
        setMessage(null);
        onPasswordChanged();
      }, 1000);
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : "Đổi mật khẩu thất bại", type: "error" });
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
          title={forced ? "Đặt mật khẩu mới" : "Đổi mật khẩu"}
          description="Đổi xong bạn sẽ đăng nhập lại; các phiên trên thiết bị khác cũng bị đăng xuất."
          onClose={forced ? undefined : close}
        />
        <DialogBody className="space-y-4">
          {message && (
            <Notice tone={message.type === "success" ? "success" : "danger"}>{message.text}</Notice>
          )}
          {forced && !message && (
            <Notice tone="warning" title="Bạn đang dùng mật khẩu tạm">
              Hãy đặt mật khẩu mới trước khi truy cập dữ liệu kinh doanh.
            </Notice>
          )}
          <Field label="Mật khẩu hiện tại" htmlFor="pwd-current">
            <PasswordInput id="pwd-current" required autoComplete="current-password" value={currentPwd}
              onChange={(e) => setCurrentPwd(e.target.value)} data-autofocus />
          </Field>
          <Field label="Mật khẩu mới" htmlFor="pwd-new" hint="Tối thiểu 10 ký tự.">
            <PasswordInput id="pwd-new" required minLength={10} autoComplete="new-password" value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)} />
          </Field>
        </DialogBody>
        <DialogFooter>
          {!forced && <Button variant="secondary" onClick={close}>Hủy</Button>}
          <Button type="submit" variant="primary" loading={submitting}>Cập nhật mật khẩu</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
