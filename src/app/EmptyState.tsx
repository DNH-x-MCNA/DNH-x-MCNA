"use client";

import type { ReactNode } from "react";
import {
  IconChart, IconCoin, IconCompare, IconHistory, IconKey, IconMapPin, IconPackage, IconTarget,
  IconTrendUp, IconUsers, IconWallet,
} from "./icons";
import { UserInfo, displayName, scopeLabel } from "./lib";
import { Button, Notice } from "./ui";

type Suggestion = { topic: string; question: string; icon: ReactNode };

const ICON = "h-[18px] w-[18px]";
const SUGGESTIONS_COMMON: Suggestion[] = [
  { topic: "Doanh thu", question: "Doanh thu hôm nay bao nhiêu?", icon: <IconTrendUp className={ICON} /> },
  { topic: "Sản phẩm", question: "Top 10 sản phẩm bán chạy nhất?", icon: <IconPackage className={ICON} /> },
  { topic: "So sánh", question: "So sánh doanh thu tháng này với tháng trước?", icon: <IconCompare className={ICON} /> },
  { topic: "KPI", question: "Nhân viên nào chưa đạt KPI?", icon: <IconTarget className={ICON} /> },
  { topic: "Công nợ", question: "Công nợ quá hạn nhiều nhất là khách hàng nào?", icon: <IconWallet className={ICON} /> },
  { topic: "Tài khoản của tôi", question: "Lịch sử truy vấn và chi phí của tôi", icon: <IconHistory className={ICON} /> },
];
const SUGGESTIONS_CLEVEL: Suggestion[] = [
  ...SUGGESTIONS_COMMON,
  { topic: "Chi phí AI", question: "Báo cáo chi phí AI toàn công ty", icon: <IconCoin className={ICON} /> },
  { topic: "Chi phí AI", question: "Báo cáo chi phí AI chi tiết theo người dùng", icon: <IconUsers className={ICON} /> },
];

export function EmptyState({ user, isAdmin, onAsk, onChangePassword, onOpenAudit, onOpenUsers }: {
  user: UserInfo;
  isAdmin: boolean;
  onAsk: (question: string) => void;
  onChangePassword: () => void;
  onOpenAudit: () => void;
  onOpenUsers: () => void;
}) {
  const pending = user.status === "pending";
  const opsOnly = user.role === "admin_ops";

  return (
    <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center px-4 py-8 sm:px-6">
      <div className="animate-rise-in">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/namha-mark.png" alt="" aria-hidden="true" className="h-11 w-11" />
        <h1 className="mt-5 text-[28px] font-semibold leading-tight tracking-tight text-navy sm:text-[32px]">
          Xin chào, {displayName(user)}
        </h1>
        <p className="mt-2 max-w-xl text-[15.5px] leading-relaxed text-slate-500">
          {opsOnly
            ? "Quản lý tài khoản nhân viên và theo dõi chi phí AI của hệ thống."
            : "Hỏi bằng tiếng Việt về doanh thu, công nợ, KPI hay tồn kho. Trợ lý tra cứu trực tiếp dữ liệu Bravo và DMS rồi trả lời kèm số liệu."}
        </p>
        {!opsOnly && !pending && (
          <div className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-sunken px-3 py-1 text-[13px] text-slate-600">
            <IconMapPin className="h-3.5 w-3.5 text-slate-400" />
            Phạm vi dữ liệu: <span className="font-medium text-slate-800">{scopeLabel(user)}</span>
          </div>
        )}
      </div>

      {pending ? (
        <Notice
          tone="warning"
          title="Tài khoản đang chờ duyệt"
          className="mt-8 animate-rise-in"
          action={<Button size="sm" variant="secondary" icon={<IconKey className="h-3.5 w-3.5" />} onClick={onChangePassword}>Đổi mật khẩu</Button>}
        >
          Quản trị viên chưa phê duyệt và phân quyền cho tài khoản này, nên bạn chưa thể hỏi dữ liệu.
          Trong lúc chờ, bạn nên đổi mật khẩu khởi tạo.
        </Notice>
      ) : opsOnly ? (
        <Notice
          tone="info"
          title="Tài khoản quản trị hệ thống"
          className="mt-8 animate-rise-in"
          action={
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" icon={<IconUsers className="h-3.5 w-3.5" />} onClick={onOpenUsers}>Tài khoản nhân viên</Button>
              <Button size="sm" variant="secondary" icon={<IconChart className="h-3.5 w-3.5" />} onClick={onOpenAudit}>Chi phí AI & nhật ký</Button>
            </div>
          }
        >
          Tài khoản này chỉ dùng để quản lý tài khoản và theo dõi chi phí, không dùng để hỏi dữ liệu kinh doanh.
        </Notice>
      ) : (
        <>
          <div className="mt-7 grid gap-2.5 sm:grid-cols-2">
            {(isAdmin ? SUGGESTIONS_CLEVEL : SUGGESTIONS_COMMON).map((s, i) => (
              <button
                key={s.question}
                type="button"
                onClick={() => onAsk(s.question)}
                style={{ animationDelay: `${60 + i * 35}ms` }}
                className="group flex animate-rise-in items-start gap-3 rounded-2xl bg-white px-3.5 py-3 text-left ring-1 ring-inset ring-line transition hover:bg-soft hover:ring-line-strong"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-brand transition group-hover:bg-brand group-hover:text-white">
                  {s.icon}
                </span>
                <span className="min-w-0">
                  <span className="block text-[12.5px] font-medium text-slate-400">{s.topic}</span>
                  <span className="mt-0.5 block text-[14.5px] leading-snug text-slate-800">{s.question}</span>
                </span>
              </button>
            ))}
          </div>
          <p className="mt-5 text-[13px] leading-relaxed text-slate-400">
            Mẹo: có thể hỏi tiếp như “còn tháng trước thì sao?” — trợ lý nhớ ngữ cảnh trong cùng cuộc trò chuyện.
          </p>
        </>
      )}
    </div>
  );
}
