"use client";

// ============================================================================
// Thanh phan giao dien dung chung (28/09/2026, thiet ke lai): moi nut, o nhap, hop thoai trong app
// deu di qua day de giu mot kieu - mot mau nhan (indigo) cho hanh dong chinh, mau trang thai chi
// dung cho trang thai.
// ============================================================================
import {
  ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, forwardRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { IconAlert, IconCheck, IconChevronDown, IconClose, IconEye, IconEyeOff, IconInfo, IconWarning } from "./icons";
import { useModal } from "./useModal";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------------------- Nut
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "dangerGhost" | "successGhost" | "dark";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand text-white shadow-sm hover:bg-brand-strong active:bg-brand-strong",
  secondary: "bg-white text-slate-800 ring-1 ring-inset ring-line-strong shadow-card hover:bg-slate-50",
  ghost: "text-slate-600 hover:bg-sunken hover:text-slate-900",
  danger: "bg-[var(--status-danger-strong)] text-white shadow-sm hover:bg-red-700",
  dangerGhost: "text-red-600 hover:bg-red-50 hover:text-red-700",
  successGhost: "text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800",
  dark: "bg-navy text-white shadow-sm hover:bg-navy-soft",
};
const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 rounded-lg px-3 text-[13px]",
  md: "h-10 gap-2 rounded-xl px-4 text-sm",
  lg: "h-11 gap-2 rounded-xl px-5 text-[15px]",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cx(
        "inline-flex shrink-0 select-none items-center justify-center font-medium transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="h-4 w-4" /> : icon}
      {children}
    </button>
  );
});

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  size?: "sm" | "md";
  tone?: "default" | "danger";
};

export function IconButton({ label, size = "md", tone = "default", className, children, type = "button", ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-40",
        tone === "danger" ? "hover:bg-red-50 hover:text-red-600" : "hover:bg-sunken hover:text-slate-900",
        size === "sm" ? "h-7 w-7" : "h-9 w-9",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cx("animate-spin", className)} aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------- O nhap
const CONTROL =
  "w-full rounded-xl bg-white text-[15px] text-slate-900 ring-1 ring-inset ring-line-strong transition " +
  "placeholder:text-slate-400 hover:ring-slate-400 focus:outline-none focus:ring-2 focus:ring-brand " +
  "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-slate-500 disabled:hover:ring-line-strong";

export function Field({ label, htmlFor, hint, trailing, children }: {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={htmlFor} className="text-[13px] font-medium text-slate-700">{label}</label>
        {trailing}
      </div>
      {children}
      {hint && <p className="text-[12.5px] leading-relaxed text-slate-500">{hint}</p>}
    </div>
  );
}

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cx(CONTROL, "h-11 px-3.5", className)} {...rest} />;
});

export function PasswordInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input type={visible ? "text" : "password"} className={cx(CONTROL, "h-11 pl-3.5 pr-11", className)} {...rest} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
        title={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
        className="absolute inset-y-0 right-1 my-auto flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:text-slate-700"
      >
        {visible ? <IconEyeOff className="h-[18px] w-[18px]" /> : <IconEye className="h-[18px] w-[18px]" />}
      </button>
    </div>
  );
}

export function Select({ className, children, compact = false, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { compact?: boolean }) {
  return (
    <div className={cx("relative", className)}>
      <select
        className={cx(
          CONTROL,
          "appearance-none pr-9",
          compact ? "h-9 rounded-lg pl-3 text-[13px]" : "h-11 pl-3.5",
        )}
        {...rest}
      >
        {children}
      </select>
      <IconChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
    </div>
  );
}

export function CompactInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(CONTROL, "h-9 rounded-lg px-3 text-[13px]", className)} {...rest} />;
}

// ---------------------------------------------------------------------------- Tab / nhan
export type SegmentOption<T extends string> = { value: T; label: ReactNode; badge?: ReactNode };

export function SegmentedControl<T extends string>({ options, value, onChange, className, label }: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className={cx("inline-flex rounded-xl bg-sunken p-1", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cx(
              "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 text-[13px] font-medium transition",
              active ? "bg-white text-slate-900 shadow-card" : "text-slate-500 hover:text-slate-800",
            )}
          >
            {o.label}
            {o.badge != null && (
              <span className={cx("rounded-md px-1.5 text-[11px] tabular-nums", active ? "bg-sunken text-slate-600" : "bg-white/70 text-slate-500")}>
                {o.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";
const BADGE_TONES: Record<Tone, string> = {
  neutral: "bg-sunken text-slate-600",
  brand: "bg-indigo-50 text-indigo-700",
  success: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-800",
  danger: "bg-red-50 text-red-700",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-[12px] font-medium", BADGE_TONES[tone], className)}>
      {children}
    </span>
  );
}

const NOTICE_TONES: Record<"info" | "success" | "warning" | "danger", { box: string; icon: ReactNode }> = {
  info: { box: "bg-slate-50 text-slate-700 ring-line", icon: <IconInfo className="h-[18px] w-[18px] text-slate-400" /> },
  success: { box: "bg-emerald-50/70 text-emerald-900 ring-emerald-200/70", icon: <IconCheck className="h-[18px] w-[18px] text-emerald-600" /> },
  warning: { box: "bg-amber-50/80 text-amber-900 ring-amber-200/80", icon: <IconWarning className="h-[18px] w-[18px] text-amber-600" /> },
  danger: { box: "bg-red-50/70 text-red-900 ring-red-200/70", icon: <IconAlert className="h-[18px] w-[18px] text-red-600" /> },
};

export function Notice({ tone = "info", title, children, action, className }: {
  tone?: keyof typeof NOTICE_TONES;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const t = NOTICE_TONES[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex gap-3 rounded-xl p-3.5 text-[13.5px] leading-relaxed ring-1 ring-inset", t.box, className)}>
      <span className="mt-px shrink-0">{t.icon}</span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cx(title ? "mt-0.5" : null, "opacity-90")}>{children}</div>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-slate-200/70", className)} />;
}

export function Avatar({ name, className }: { name: string; className?: string }) {
  // Nguoi Viet goi nhau bang ten (tu cuoi): "Tran Minh Long" -> "L".
  const words = name.trim().split(/\s+/);
  const letter = (words[words.length - 1] || name).charAt(0).toUpperCase();
  return (
    <span className={cx("flex shrink-0 items-center justify-center rounded-full bg-navy text-[13px] font-semibold text-white", className)} aria-hidden="true">
      {letter}
    </span>
  );
}

// ---------------------------------------------------------------------------- Hop thoai
const DIALOG_SIZES = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-xl",
  xl: "sm:max-w-5xl",
  full: "sm:max-w-6xl",
};

/** Hop thoai render qua portal ra <body>: hop thoai long nhau (vd tao tai khoan ben trong quan ly
 *  tai khoan) khong bi `transform` cua hop thoai cha lam lech vi tri `position: fixed`.
 *  `trap=false` khi dang co hop thoai con mo, de Esc/Tab chi tac dong len hop thoai tren cung. */
export function Dialog({ open, onClose, labelledBy, size = "md", trap = true, closeOnBackdrop = true, className, children }: {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  size?: keyof typeof DIALOG_SIZES;
  trap?: boolean;
  closeOnBackdrop?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const ref = useModal(open && trap, onClose);
  // Hop thoai chi mo sau khi dang nhap (chay tren trinh duyet), nhung van chan truong hop render phia
  // server de createPortal khong goi toi `document`.
  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
      <div
        className="absolute inset-0 animate-fade-in bg-slate-950/40 backdrop-blur-[2px]"
        onClick={closeOnBackdrop ? onClose : undefined}
        aria-hidden="true"
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={cx(
          "relative flex max-h-[94dvh] w-full animate-dialog-in flex-col overflow-hidden rounded-t-2xl bg-white shadow-float outline-none ring-1 ring-slate-900/5 sm:max-h-[88vh] sm:rounded-2xl",
          DIALOG_SIZES[size],
          className,
        )}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function DialogHeader({ id, title, description, icon, onClose, actions }: {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  onClose: () => void;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
      {icon && (
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-brand">{icon}</span>
      )}
      <div className="min-w-0 flex-1">
        <h2 id={id} className="text-[17px] font-semibold tracking-tight text-navy">{title}</h2>
        {description && <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>}
      </div>
      {actions && <div className="hidden items-center gap-2 sm:flex">{actions}</div>}
      <IconButton label="Đóng" onClick={onClose} className="-mr-1.5 -mt-0.5">
        <IconClose className="h-5 w-5" />
      </IconButton>
    </div>
  );
}

export function DialogBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("custom-scroll min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6", className)}>{children}</div>;
}

export function DialogFooter({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cx("flex flex-wrap items-center justify-end gap-2 border-t border-line bg-soft px-5 py-3.5 sm:px-6", className)}>
      {children}
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onCancel }: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} labelledBy="confirm-dialog-title" size="sm">
      <div className="px-5 pb-2 pt-5 sm:px-6">
        <h2 id="confirm-dialog-title" className="text-[17px] font-semibold tracking-tight text-navy">{title}</h2>
        <div className="mt-1.5 text-[14px] leading-relaxed text-slate-600">{message}</div>
      </div>
      <div className="flex justify-end gap-2 px-5 pb-5 pt-4 sm:px-6">
        <Button variant="secondary" onClick={onCancel} data-autofocus>Hủy</Button>
        <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Dialog>
  );
}
