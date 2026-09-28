"use client";

import { FormEvent, KeyboardEvent, forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { IconSend, IconSquare } from "./icons";
import type { UserInfo } from "./lib";
import { cx } from "./ui";

export type ComposerHandle = { focus: () => void };

export const Composer = forwardRef<ComposerHandle, {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  loading: boolean;
  disabledReason: string | null;
  quota: Pick<UserInfo, "quota_limit" | "quota_remaining" | "quota_resets_at">;
}>(function Composer({ value, onChange, onSubmit, onStop, loading, disabledReason, quota }, ref) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }), []);

  // O nhap tu gian theo noi dung (toi da ~8 dong), tro ve 1 dong khi gui xong.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  const disabled = Boolean(disabledReason);
  const canSend = !disabled && !loading && value.trim().length > 0;

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // isComposing: bo go tieng Viet (Telex/VNI tren macOS, IME) dang ghep dau - Enter luc do la chot
    // chu, khong phai gui cau hoi.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (canSend) onSubmit();
  }

  const limit = quota.quota_limit;
  const remaining = quota.quota_remaining ?? 0;
  const quotaTone =
    limit == null ? "" : remaining === 0 ? "text-red-600" : remaining <= limit * 0.2 ? "text-amber-700" : "text-slate-400";

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl px-3 pb-3 sm:px-6 sm:pb-5">
      <div
        className={cx(
          "rounded-[22px] bg-white shadow-composer ring-1 ring-inset ring-line transition",
          !disabled && "focus-within:ring-2 focus-within:ring-brand/60",
          disabled && "bg-soft",
        )}
      >
        <label htmlFor="composer-input" className="sr-only">Câu hỏi cho trợ lý</label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabledReason || "Hỏi về doanh thu, công nợ, KPI, tồn kho…"}
          className="custom-scroll block max-h-[220px] w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-[15px] leading-relaxed text-navy outline-none placeholder:text-slate-400 disabled:cursor-not-allowed sm:px-5"
        />
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5 pt-1 sm:px-4">
          <span className="hidden text-[12px] text-slate-400 sm:inline">
            {disabled ? "" : "Enter để gửi · Shift + Enter để xuống dòng"}
          </span>
          <div className="ml-auto flex items-center gap-3">
            {limit != null && (
              <span
                className={cx("text-[12.5px] font-medium tabular-nums", quotaTone)}
                title={quota.quota_resets_at ? `Làm mới lúc ${new Date(quota.quota_resets_at).toLocaleString("vi-VN")}` : undefined}
              >
                Còn {remaining}/{limit} câu tuần này
              </span>
            )}
            {loading ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Dừng trả lời"
                title="Dừng trả lời"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-navy text-white transition hover:bg-navy-soft active:scale-95"
              >
                <IconSquare className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSend}
                aria-label="Gửi câu hỏi"
                title="Gửi câu hỏi"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-brand text-white transition hover:bg-brand-strong active:scale-95 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
              >
                <IconSend className="h-[18px] w-[18px]" />
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="mt-2 hidden text-center text-[11.5px] text-slate-400 sm:block">
        Trợ lý có thể nhầm. Với số liệu quan trọng, hãy mở “Xem truy vấn đã dùng” để đối chiếu.
      </p>
    </form>
  );
});
