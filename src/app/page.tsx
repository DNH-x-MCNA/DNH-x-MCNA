"use client";

import { useState, useRef, useEffect, useMemo, memo, FormEvent, ReactNode, RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AuthScreens from "./AuthScreens";
import AdminUsersPanel from "./AdminUsersPanel";

type ChatResponse = {
  answer: string;
  sql_used: string[];
  columns: string[] | null;
  rows: unknown[][] | null;
  row_count: number | null;
};

// Tỷ giá USD -> VND cho các số chi phí AI hiển thị ở frontend. Phải khớp với
// backend/pricing.py::USD_TO_VND_RATE — backend trả sẵn *_vnd cho phần lớn số liệu, riêng phần
// "chưa quy được cho ai" đang quy đổi tại đây nên vẫn cần hằng số này.
const USD_TO_VND_RATE = 26334.5;

type HistoryMessage = { role: "user" | "assistant"; content: string };

type SessionSummary = {
  session_id: string;
  title: string | null;
  owner_username: string;
  owner_name: string | null;
  created_at: string;
  updated_at: string;
};

// ============================================================================
// Icon SVG nhẹ (tự vẽ, không phụ thuộc thư viện ngoài) — dùng cho header, sidebar,
// ô nhập và modal Audit Log theo yêu cầu Executive Light Theme 29/07/2026.
// ============================================================================
type IconProps = { className?: string };
const IconChart = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const IconLogout = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const IconPlus = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" />
  </svg>
);
const IconTrash = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const IconSend = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 20 20.5 12 4 4l2.5 7.2L4 20Zm2.5-7.8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const IconSearch = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
    <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
const IconUsers = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="9" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8" />
    <path d="M2.8 19c.6-3.2 3.2-5 6.2-5s5.6 1.8 6.2 5M16 8.3a3 3 0 1 1 3.6 4.9M19 13.4c2.2.5 3.7 2 4.2 4.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
const IconCoin = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
    <path d="M12 7v10M9.5 9.3c0-1.1 1.1-2 2.5-2s2.5.7 2.5 1.7c0 2.3-5 1.4-5 3.7 0 1 1.1 1.7 2.5 1.7s2.5-.9 2.5-2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);
const IconMenu = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
const IconClose = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
const IconRefresh = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M20 11A8 8 0 1 0 18.5 16M20 5v6h-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// Tag mau co dinh cho ky hieu kenh/vung xuat hien DUNG NGUYEN VAN trong 1 o bang - chi khop chinh
// xac (sau khi trim), KHONG doan/parse noi dung cau tra loi cua AI nen khong co rui ro hien sai so
// lieu. Cell nao khong khop 1 trong cac khoa nay se render binh thuong nhu truoc.
const CHANNEL_REGION_TAG_STYLES: Record<string, string> = {
  ETC: "bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-200",
  OTC: "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-200",
  "Miền Bắc": "bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200",
  "Miền Nam": "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200",
  "Miền Trung": "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200",
};

// Chuoi CHI la so/phan tram/tien te (vd "177,88 tỷ", "42,5%", "3,010,403") - dung de quyet dinh can
// phai 1 o bang. Cau chu binh thuong (co chua chu cai khac ngoai don vi tien te) se khong khop, nen
// khong co rui ro can le nham vao van ban.
function isNumericLikeCell(text: string): boolean {
  return /^[+-]?[\d.,]+\s*(%|đ|vnd|usd|tỷ|triệu|nghìn|k|đ\/usd)?$/i.test(text.trim());
}

// Rut chuoi thuan tuy tu children cua react-markdown NEU no chi gom text node (khong co the <strong>,
// <a>... long ben trong) - dung de quyet dinh co ap dung tag/can-phai hay khong. Cell phuc tap hon
// (vd co chu in dam) se tra ve null va giu nguyen cach render mac dinh, an toan hon la doan sai.
function getPlainCellText(children: ReactNode): string | null {
  const arr = Array.isArray(children) ? children : [children];
  if (arr.length !== 1 || typeof arr[0] !== "string") return null;
  return arr[0];
}

// Cho bang co CAU TRUC that (m.rows/m.columns tra ve tu SQL, khong phai text AI sinh ra) - xet ca
// CỘT thay vi tung o rieng le vi o day co du lieu goc (number hoac string) nen do tin cay cao hon.
// Mot cot duoc coi la "so" neu >=80% gia tri khac rong khop dang so - dong nhat ca cot thay vi
// can-phai roi rac tung dong.
function isNumericCellValue(v: unknown): boolean {
  if (typeof v === "number") return true;
  if (typeof v === "string") return isNumericLikeCell(v);
  return false;
}
function numericColumnFlags(rows: unknown[][], colCount: number): boolean[] {
  const flags: boolean[] = [];
  for (let c = 0; c < colCount; c++) {
    const vals = rows.map((r) => r[c]).filter((v) => v !== null && v !== undefined && v !== "");
    flags.push(vals.length > 0 && vals.filter(isNumericCellValue).length / vals.length >= 0.8);
  }
  return flags;
}

// Kieu toi gian cho node cua cay markdown (mdast) - chi khai bao truong can dung, tranh phai them
// dependency @types/mdast rieng chi de dung 1 remark plugin nho.
type MdastLikeNode = {
  type: string;
  children?: MdastLikeNode[];
  value?: string;
  align?: (string | null)[];
};

function mdastPlainText(node: MdastLikeNode): string {
  if (node.type === "text" || node.type === "inlineCode") return node.value || "";
  if (!node.children) return "";
  return node.children.map(mdastPlainText).join("");
}

// Remark plugin: xet CA COT (gom header) cua bang markdown do AI sinh ra, thay vi can-phai tung o
// <td> rieng le. Ly do sua: can-phai tung o khien tieu de cot ("Doanh thu") nam ben trai trong khi
// so lieu ben duoi nam ben phai - nhin giong bi lech hang du moi o rieng le van dung. Ap dung style
// text-align qua thuoc tinh "align" chuan cua mdast (giong cach remark-gfm xu ly cu phap `---:` trong
// markdown) nen header va du lieu LUON can theo dung 1 kieu.
function remarkAlignNumericColumns() {
  return (tree: MdastLikeNode) => {
    const visit = (node: MdastLikeNode) => {
      if (node.type === "table" && Array.isArray(node.children) && node.children.length >= 2) {
        const rows = node.children; // hang dau la header
        const colCount = rows[0].children?.length ?? 0;
        const align: (string | null)[] =
          node.align && node.align.length === colCount ? [...node.align] : new Array(colCount).fill(null);
        for (let c = 0; c < colCount; c++) {
          const texts = rows
            .slice(1)
            .map((r) => r.children?.[c])
            .filter((cell): cell is MdastLikeNode => Boolean(cell))
            .map((cell) => mdastPlainText(cell).trim())
            .filter((t) => t !== "" && t !== "—" && t !== "-");
          if (texts.length === 0) continue;
          if (texts.filter(isNumericLikeCell).length / texts.length >= 0.8) align[c] = "right";
        }
        node.align = align;
      }
      (node.children || []).forEach(visit);
    };
    visit(tree);
  };
}

function formatRelativeTime(iso: string): string {
  // Backend luu "YYYY-MM-DD HH:MM:SS" theo gio local server (khong co timezone suffix) - parse thu
  // cong the la ISO-ish, cach nay du chinh xac cho hien thi "may phut/gio truoc".
  const d = new Date(iso.replace(" ", "T"));
  if (isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "vừa xong";
  if (mins < 60) return `${mins} phút trước`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} ngày trước`;
  return d.toLocaleDateString("vi-VN");
}

// Nhom danh sach cuoc tro chuyen theo moc thoi gian "Hom nay / 7 ngay qua / Cu hon" de hien thi
// trong sidebar - dua tren updated_at (cung dinh dang "YYYY-MM-DD HH:MM:SS" nhu formatRelativeTime).
type SessionGroup = { label: string; items: SessionSummary[] };
function groupSessionsByDate(list: SessionSummary[]): SessionGroup[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const sevenDaysAgo = startOfToday - 7 * 86400000;

  const today: SessionSummary[] = [];
  const last7Days: SessionSummary[] = [];
  const older: SessionSummary[] = [];

  for (const s of list) {
    const d = new Date(s.updated_at.replace(" ", "T"));
    const t = isNaN(d.getTime()) ? 0 : d.getTime();
    if (t >= startOfToday) today.push(s);
    else if (t >= sevenDaysAgo) last7Days.push(s);
    else older.push(s);
  }

  return [
    { label: "Hôm nay", items: today },
    { label: "7 ngày qua", items: last7Days },
    { label: "Cũ hơn", items: older },
  ].filter((g) => g.items.length > 0);
}

type Message = {
  role: "user" | "bot";
  text: string;
  sqlUsed?: string[];
  columns?: string[] | null;
  rows?: unknown[][] | null;
  error?: boolean;
};

const SAMPLE_QUESTIONS_COMMON = [
  "Doanh thu hôm nay bao nhiêu?",
  "Top 10 sản phẩm bán chạy nhất?",
  "So sánh doanh thu tháng này với tháng trước?",
  "Nhân viên nào chưa đạt KPI?",
  "Công nợ quá hạn nhiều nhất là khách hàng nào?",
  "Lịch sử truy vấn và chi phí của tôi",
];

const SAMPLE_QUESTIONS_CLEVEL = [
  ...SAMPLE_QUESTIONS_COMMON,
  "Báo cáo chi phí AI toàn công ty",
  "Báo cáo chi phí AI chi tiết theo người dùng",
];

// Icon cho chip cau hoi goi y - chi doan theo tu khoa de trang tri (khong anh huong noi dung cau hoi
// thuc gui di), fallback ve icon mac dinh neu khong khop tu khoa nao.
function chipIcon(question: string): string {
  const q = question.toLowerCase();
  if (q.includes("chi phí ai")) return "💰";
  if (q.includes("công nợ")) return "📊";
  if (q.includes("kpi")) return "🎯";
  if (q.includes("doanh thu") || q.includes("doanh số")) return "⚡";
  if (q.includes("sản phẩm")) return "📦";
  if (q.includes("so sánh")) return "🔁";
  return "💬";
}

// Goi vao route noi bo (/api/...) cua chinh Next.js thay vi goi thang backend - route nay chay
// server-side tren Vercel, giu BACKEND_API_URL/BACKEND_API_KEY (khong phai NEXT_PUBLIC_) nen trinh
// duyet khong bao gio thay duoc URL that/API key cua backend.
const API_URL = "/api";
const SESSION_KEY = "dnh_chat_session_id";
const AUTH_TOKEN_KEY = "dnh_auth_token";

function authHeaders(token: string | null): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

type UserInfo = {
  username: string;
  name: string | null;
  role: string;
  scope_value: string | null;
  scope_channel?: string | null;
  status?: string;
  email?: string | null;
};

type AuditSummary = {
  total_cost_usd: number;
  total_cost_vnd: number;
  attributed_cost_usd: number;
  unattributed_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_tokens: number;
  grand_total_tokens: number;
  total_queries: number;
  unique_users_count: number;
  days: number;
};

type UserBreakdownItem = {
  username: string;
  user_name: string;
  query_count: number;
  input_tokens: number;
  output_tokens: number;
  // cache_tokens/is_unattributed do backend bo sung 29/07/2026 - de optional de dashboard khong vo
  // khi frontend da deploy nhung backend tren may 24 con chay ban cu.
  cache_tokens?: number;
  total_tokens: number;
  cost_usd: number;
  cost_vnd: number;
  is_unattributed?: boolean;
};

type WeeklyDailyItem = {
  day_index: number;
  day_name: string;
  date_str: string;
  display_date: string;
  is_today: boolean;
  query_count: number;
  input_tokens: number;
  output_tokens: number;
  cache_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_vnd: number;
};

type WeeklyUserItem = {
  username: string;
  user_name: string;
  query_count: number;
  total_tokens: number;
  cost_usd: number;
  cost_vnd: number;
};

type WeeklyAuditData = {
  week_offset: number;
  week_start: string;
  week_end: string;
  week_label: string;
  is_current_week: boolean;
  total_queries: number;
  total_tokens: number;
  total_cost_usd: number;
  total_cost_vnd: number;
  daily_breakdown: WeeklyDailyItem[];
  user_breakdown: WeeklyUserItem[];
};

// Cac truong session_* la so cua CA PHIEN chat, khong phai cua rieng luot hoi tren dong do:
// cost_log ghi theo tung lan goi API, mot luot hoi sinh nhieu lan goi nen khong tach duoc xuong
// tung cau hoi. Nhieu dong cung mot phien se hien CUNG mot so - dung cong tay cac dong nay lai,
// tong dung nam o phan summary (da chong trung).
type QueryLogItem = {
  ts: string;
  username: string;
  user_name: string;
  question: string;
  sql: string | null;
  status: string;
  duration_ms: number | null;
  session_id: string | null;
  session_input_tokens: number;
  session_output_tokens: number;
  session_total_tokens: number;
  session_cost_usd: number;
  session_cost_vnd: number;
};

type AuditDashboardData = {
  summary: AuditSummary;
  user_breakdown: UserBreakdownItem[];
  logs: QueryLogItem[];
};


const ROLE_LABELS: Record<string, string> = {
  admin_ops: "Admin Vận Hành (Hệ thống)",
  c_level: "Tổng Giám Đốc (C-Level)",
  regional_director: "Giám đốc Miền / Kênh",
  qlv: "Quản lý Vùng (QLV)",
};

// Style rieng cho tung the Markdown trong bong bong chat cua bot (bang, in dam, danh sach...)
const markdownComponents = {
  p: ({ children }: { children?: ReactNode }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
  strong: ({ children }: { children?: ReactNode }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  ul: ({ children }: { children?: ReactNode }) => <ul className="mb-2 ml-4 list-disc space-y-1 last:mb-0">{children}</ul>,
  ol: ({ children }: { children?: ReactNode }) => <ol className="mb-2 ml-4 list-decimal space-y-1 last:mb-0">{children}</ol>,
  li: ({ children }: { children?: ReactNode }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }: { children?: ReactNode }) => <h1 className="mb-2 mt-1 text-base font-bold text-slate-900">{children}</h1>,
  h2: ({ children }: { children?: ReactNode }) => <h2 className="mb-2 mt-1 text-sm font-bold text-slate-900">{children}</h2>,
  h3: ({ children }: { children?: ReactNode }) => <h3 className="mb-1 mt-1 text-sm font-semibold text-slate-900">{children}</h3>,
  code: ({ children }: { children?: ReactNode }) => (
    <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs text-slate-800">{children}</code>
  ),
  hr: () => <hr className="my-3 border-slate-200" />,
  table: ({ children }: { children?: ReactNode }) => (
    <div className="mb-2 mt-1 overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
      <table className="min-w-full text-xs tabular-nums">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => <thead className="bg-[#F1F5F9]">{children}</thead>,
  tbody: ({ children }: { children?: ReactNode }) => <tbody className="divide-y divide-slate-100 bg-white">{children}</tbody>,
  tr: ({ children }: { children?: ReactNode }) => <tr className="transition hover:bg-slate-50">{children}</tr>,
  // mdast-util-to-hast tao thuoc tinh HAST "align" (cu) tu truong "align" cua mdast ma
  // remarkAlignNumericColumns gan (xet CA COT). react-markdown roi chuyen thuoc tinh HAST "align" do
  // THANH prop `style={{textAlign}}` khi tao React element - da xac minh bang render thu (khong phai
  // prop `align` nhu doc source mdast-util-to-hast tuong tuong) - phai nhan `style`, khong duoc chi
  // destructure {children} roi bo qua, neu khong tieu de cot se khong can theo du lieu ben duoi.
  th: ({ children, style }: { children?: ReactNode; style?: React.CSSProperties }) => (
    <th className={`px-3 py-2 font-semibold text-slate-600 ${style?.textAlign === "right" ? "text-right" : "text-left"}`}>
      {children}
    </th>
  ),
  // Tag mau cho o chi chua dung 1 khoa kenh/vung - chi ap dung khi getPlainCellText tra ve chuoi
  // thuan (khong co the long ben trong), neu khong khop thi giu nguyen cach render mac dinh.
  td: ({ children, style }: { children?: ReactNode; style?: React.CSSProperties }) => {
    const text = getPlainCellText(children);
    const trimmed = text?.trim();
    const tagClass = trimmed ? CHANNEL_REGION_TAG_STYLES[trimmed] : undefined;
    if (tagClass) {
      return (
        <td className="px-3 py-2">
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${tagClass}`}>
            {trimmed}
          </span>
        </td>
      );
    }
    return (
      <td className={`px-3 py-2 text-slate-700 ${style?.textAlign === "right" ? "text-right" : "text-left"}`}>
        {children}
      </td>
    );
  },
};

// Tach rieng khoi Home() + boc React.memo: Home() co state `input` doi moi lan go phim, neu khung
// tin nhan nam chung component se bi ve lai TOAN BO (ke ca parse lai markdown/bang cua moi tin nhan
// cu) moi lan go 1 ky tu - cang nhieu tin nhan cang lag. Component rieng nay CHI ve lai khi `messages`
// hoac `loading` thuc su doi (gui/nhan tin moi), khong bi anh huong boi viec go chu.
const MessageList = memo(function MessageList({
  messages,
  loading,
  bottomRef,
}: {
  messages: Message[];
  loading: boolean;
  bottomRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="flex flex-col gap-4">
      {messages.map((m, i) => (
        <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[85%] text-sm leading-relaxed ${
              m.role === "user"
                ? "bg-gradient-to-r from-blue-700 to-indigo-800 text-white shadow-md rounded-2xl rounded-tr-none px-4 py-3 font-medium"
                : m.error
                ? "bg-amber-50 text-amber-900 border-l-4 border-amber-500 shadow-sm rounded-2xl rounded-tl-none p-4"
                : "bg-white text-slate-800 border border-slate-200/80 shadow-sm rounded-2xl rounded-tl-none p-4"
            }`}
          >
            {m.role === "bot" ? (
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkAlignNumericColumns]} components={markdownComponents}>
                  {m.text}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="whitespace-pre-wrap">{m.text}</div>
            )}

            {m.rows && m.columns && m.rows.length > 0 && (() => {
              const numericCols = numericColumnFlags(m.rows, m.columns.length);
              return (
                <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
                  <table className="min-w-full text-xs tabular-nums">
                    <thead className="bg-[#F1F5F9]">
                      <tr>
                        {m.columns.map((c, ci) => (
                          <th
                            key={c}
                            className={`px-3 py-2 font-semibold text-slate-600 ${numericCols[ci] ? "text-right" : "text-left"}`}
                          >
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {m.rows.map((row, ri) => (
                        <tr key={ri} className="transition hover:bg-slate-50">
                          {row.map((cell, ci) => {
                            const cellText = cell === null ? "—" : String(cell);
                            const tagClass = CHANNEL_REGION_TAG_STYLES[cellText];
                            return (
                              <td
                                key={ci}
                                className={`px-3 py-2 text-slate-700 ${!tagClass && numericCols[ci] ? "text-right" : "text-left"}`}
                              >
                                {tagClass ? (
                                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${tagClass}`}>
                                    {cellText}
                                  </span>
                                ) : (
                                  cellText
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}

            {m.sqlUsed && m.sqlUsed.length > 0 && (
              <details className="mt-2 text-xs text-slate-400">
                <summary className="cursor-pointer select-none hover:text-slate-600">
                  Xem truy vấn đã dùng (để kiểm chứng)
                </summary>
                {m.sqlUsed.map((sql, si) => (
                  <pre key={si} className="mt-1 overflow-x-auto rounded bg-slate-900 p-2 text-slate-100">
                    {sql}
                  </pre>
                ))}
              </details>
            )}
          </div>
        </div>
      ))}

      {loading && (
        <div className="flex justify-start">
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-400 shadow-sm">
            <span className="flex gap-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
            </span>
            Đang truy vấn dữ liệu...
          </div>
        </div>
      )}
      <div ref={bottomRef} />


    </div>
  );
});

function sessionKeyFor(username: string): string {
  // Rieng key theo tung username - tranh truong hop 2 tai khoan khac nhau dung chung 1 trinh duyet
  // (vd dang xuat roi dang nhap tai khoan khac) vo tinh dung chung 1 session_id cu, dan den bi 403
  // "khong co quyen xem cuoc tro chuyen nay" vi session_id do la cua nguoi dung TRUOC.
  return `${SESSION_KEY}_${username}`;
}

function getOrCreateSessionId(username: string): string {
  if (typeof window === "undefined") return "default";
  const key = sessionKeyFor(username);
  let sid = window.localStorage.getItem(key);
  if (!sid) {
    sid = crypto.randomUUID();
    window.localStorage.setItem(key, sid);
  }
  return sid;
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string>("default");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Danh sach cuoc tro chuyen (kieu ChatGPT) - c_level thay cua tat ca nguoi, con lai chi thay cua
  // chinh minh (loc o backend, xem GET /sessions trong main.py).
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Loc lich su tro chuyen theo nguoi dung. Chi C-Level moi thay nhieu chu so huu trong `sessions`,
  // nen bo loc cung chi hien voi ho - tai khoan thuong luon chi co dung 1 chu so huu la chinh minh.
  const [ownerFilter, setOwnerFilter] = useState<string>("all");

  // Trang thai dang nhap - kiem tra token da luu truoc khi cho vao giao dien chat
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginSubmitting, setLoginSubmitting] = useState(false);
  // Audit Log & Cost Dashboard Modal State
  const [auditModalOpen, setAuditModalOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditData, setAuditData] = useState<AuditDashboardData | null>(null);
  const [auditDays, setAuditDays] = useState<number>(30);
  const [auditUserFilter, setAuditUserFilter] = useState<string>("all");
  const [auditActiveTab, setAuditActiveTab] = useState<"users" | "weekly" | "logs">("users");
  const [weeklyData, setWeeklyData] = useState<WeeklyAuditData | null>(null);
  const [weeklyOffset, setWeeklyOffset] = useState<number>(0);
  const [weeklyLoading, setWeeklyLoading] = useState<boolean>(false);

  // Admin & Change Password Modal States
  const [adminUsersOpen, setAdminUsersOpen] = useState(false);
  const [changePwdOpen, setChangePwdOpen] = useState(false);
  const [currentPwdInput, setCurrentPwdInput] = useState("");
  const [newPwdInput, setNewPwdInput] = useState("");
  const [pwdChangeMsg, setPwdChangeMsg] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [pwdChangeSubmitting, setPwdChangeSubmitting] = useState(false);

  // 28/07/2026: CHI dua vao role, KHONG suy quyen tu chuoi username nua (truoc day con nhan
  // username === "c_level" || username === "dnh"). Day la ban sao o tang giao dien cua lo hong R-I
  // vua va o backend: suy quyen tu TEN tai khoan nghia la them tai khoan ten "dnh.marketing" hay
  // "c_level.tro.ly" la tu nhien thay nut xem chi phi toan cong ty. O frontend hau qua nhe hon
  // (chi an/hien nut, quyen that da chan o backend qua scope_role) nhung van phai sua cho nhat quan.
  const isCLevel = Boolean(
    userInfo && (
      userInfo.role?.toLowerCase() === "c_level" ||
      userInfo.role?.toLowerCase() === "admin" ||
      userInfo.role?.toLowerCase() === "admin_ops"
    )
  );

  const isOpsAdmin = Boolean(
    userInfo && userInfo.role?.toLowerCase() === "admin_ops"
  );

  // Danh sach chu so huu co trong lich su, kem so cuoc tro chuyen - dung dung nguon `sessions` dang
  // hien thi nen con so trong bo loc luon khop voi so dong ben duoi. Minh luon dung dau danh sach.
  const sessionOwners = useMemo(() => {
    const byUser = new Map<string, { username: string; label: string; count: number }>();
    for (const s of sessions) {
      const existing = byUser.get(s.owner_username);
      if (existing) {
        existing.count += 1;
      } else {
        byUser.set(s.owner_username, {
          username: s.owner_username,
          label: s.owner_name || s.owner_username,
          count: 1,
        });
      }
    }
    return Array.from(byUser.values()).sort((a, b) => {
      if (a.username === userInfo?.username) return -1;
      if (b.username === userInfo?.username) return 1;
      return a.label.localeCompare(b.label, "vi");
    });
  }, [sessions, userInfo?.username]);

  // Neu nguoi dang duoc loc khong con cuoc tro chuyen nao (vd vua xoa het), tu dong coi nhu "tat ca"
  // thay vi de o select rong tro tren man hinh.
  const effectiveOwnerFilter =
    ownerFilter !== "all" && !sessionOwners.some((o) => o.username === ownerFilter)
      ? "all"
      : ownerFilter;

  const visibleSessions = useMemo(
    () =>
      effectiveOwnerFilter === "all"
        ? sessions
        : sessions.filter((s) => s.owner_username === effectiveOwnerFilter),
    [sessions, effectiveOwnerFilter]
  );

  const fetchAuditData = (daysVal: number, userVal: string) => {
    if (!authToken) return;
    setAuditLoading(true);
    const params = new URLSearchParams({ days: String(daysVal), limit: "300" });
    if (userVal && userVal !== "all") {
      params.append("user_filter", userVal);
    }
    fetch(`${API_URL}/audit-logs?${params.toString()}`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: AuditDashboardData | null) => {
        if (data) setAuditData(data);
      })
      .catch((e) => console.error("Error fetching audit logs:", e))
      .finally(() => setAuditLoading(false));
  };

  const fetchWeeklyAuditData = (offset: number) => {
    if (!authToken) return;
    setWeeklyLoading(true);
    fetch(`${API_URL}/audit-logs/weekly?week_offset=${offset}`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: WeeklyAuditData | null) => {
        if (data) setWeeklyData(data);
      })
      .catch((e) => console.error("Error fetching weekly audit logs:", e))
      .finally(() => setWeeklyLoading(false));
  };

  useEffect(() => {
    if (auditModalOpen && auditActiveTab === "weekly") {
      fetchWeeklyAuditData(weeklyOffset);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auditModalOpen, auditActiveTab, weeklyOffset]);

  const openAuditDashboard = () => {
    setAuditModalOpen(true);
    fetchAuditData(auditDays, auditUserFilter);
    fetchWeeklyAuditData(weeklyOffset);
  };


  // Kiem tra token da luu (neu co) ngay khi mo trang - xac nhan qua /auth/me truoc khi cho vao chat
  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(AUTH_TOKEN_KEY) : null;
    if (!saved) {
      setAuthChecking(false);
      return;
    }
    fetch(`${API_URL}/auth/me`, { headers: authHeaders(saved) })
      .then((r) => (r.ok ? r.json() : null))
      .then((info: UserInfo | null) => {
        if (info) {
          setAuthToken(saved);
          setUserInfo(info);
        } else {
          window.localStorage.removeItem(AUTH_TOKEN_KEY);
        }
      })
      .catch(() => {})
      .finally(() => setAuthChecking(false));
  }, []);

  function refreshSessions() {
    if (!authToken) return;
    fetch(`${API_URL}/sessions`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: SessionSummary[]) => setSessions(list))
      .catch(() => {});
  }

  function loadSessionHistory(sid: string) {
    setHistoryLoaded(false);
    fetch(`${API_URL}/history/${sid}`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : []))
      .then((history: HistoryMessage[]) => {
        setMessages(
          history.map((h) => ({
            role: h.role === "user" ? "user" : "bot",
            text: h.content,
          }))
        );
      })
      .catch(() => {})
      .finally(() => setHistoryLoaded(true));
  }

  // Khoi tao session + nap lai lich su hoi thoai cu (neu co) + danh sach cuoc tro chuyen khi mo
  // trang - CHI sau khi dang nhap xong
  useEffect(() => {
    if (!authToken || !userInfo) return;
    const sid = getOrCreateSessionId(userInfo.username);
    setSessionId(sid);
    loadSessionHistory(sid);
    refreshSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken, userInfo]);

  function switchToSession(sid: string) {
    if (sid === sessionId) {
      setSidebarOpen(false);
      return;
    }
    if (userInfo) window.localStorage.setItem(sessionKeyFor(userInfo.username), sid);
    setSessionId(sid);
    loadSessionHistory(sid);
    setSidebarOpen(false);
  }

  async function deleteSession(sid: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm("Xóa cuộc trò chuyện này? Không thể hoàn tác.")) return;
    try {
      await fetch(`${API_URL}/sessions/${sid}`, { method: "DELETE", headers: authHeaders(authToken) });
    } catch {
      // bo qua loi xoa
    }
    setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    if (sid === sessionId) {
      startNewConversation();
    }
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    if (!loginUsername.trim() || !loginPassword || loginSubmitting) return;
    setLoginSubmitting(true);
    setLoginError("");
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUsername.trim(), password: loginPassword }),
      });
      if (!res.ok) {
        throw new Error("Tài khoản hoặc mật khẩu không đúng");
      }
      const data = await res.json();
      window.localStorage.setItem(AUTH_TOKEN_KEY, data.token);
      setAuthToken(data.token);
      setUserInfo({ username: loginUsername.trim(), name: data.name, role: data.role, scope_value: data.scope_value });
      setLoginPassword("");
    } catch (e) {
      setLoginError((e as Error).message);
    } finally {
      setLoginSubmitting(false);
    }
  }

  async function handleLogout() {
    if (authToken) {
      try {
        await fetch(`${API_URL}/auth/logout`, { method: "POST", headers: authHeaders(authToken) });
      } catch {
        // bo qua loi logout phia server - van xoa token cuc bo
      }
    }
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    setAuthToken(null);
    setUserInfo(null);
    setMessages([]);
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendQuestion(question: string) {
    if (!question.trim() || loading) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: authHeaders(authToken),
        body: JSON.stringify({ question, session_id: sessionId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Lỗi không xác định" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: ChatResponse = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: data.answer,
          sqlUsed: data.sql_used,
          columns: data.columns,
          rows: data.rows,
        },
      ]);
      refreshSessions();
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: `Xin lỗi, có lỗi xảy ra: ${(e as Error).message}`, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function startNewConversation() {
    if (loading) return;
    // KHONG xoa cuoc cu (khac hanh vi truoc day) - chi tao session moi va chuyen sang, cuoc cu van
    // con nguyen trong sidebar de xem lai sau, giong ChatGPT.
    const newSid = crypto.randomUUID();
    if (userInfo) window.localStorage.setItem(sessionKeyFor(userInfo.username), newSid);
    setSessionId(newSid);
    setMessages([]);
    setHistoryLoaded(true);
    setSidebarOpen(false);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendQuestion(input);
  }

  if (authChecking) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 text-sm text-slate-400">
        Đang kiểm tra đăng nhập...
      </div>
    );
  }

  if (!authToken || !userInfo) {
    return (
      <AuthScreens
        onLoginSuccess={(token, user) => {
          if (typeof window !== "undefined") {
            window.localStorage.setItem(AUTH_TOKEN_KEY, token);
          }
          setAuthToken(token);
          setUserInfo({
            username: user.username,
            name: user.name,
            role: user.role,
            scope_value: user.scope_value,
            scope_channel: user.scope_channel,
            status: user.status,
            email: user.email,
          });
        }}
      />
    );
  }

  const sessionGroups = groupSessionsByDate(visibleSessions);

  return (
    <div className="flex h-screen bg-[var(--surface-soft)]">
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-20 bg-black/30 md:hidden"
        />
      )}
      <aside
        className={`${sidebarOpen ? "fixed inset-y-0 left-0 z-30 flex" : "hidden"} w-72 flex-shrink-0 flex-col border-r border-slate-200 bg-white md:static md:z-0 md:flex`}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4">
          <span className="text-sm font-semibold text-slate-700">Lịch sử trò chuyện</span>
          <button onClick={() => setSidebarOpen(false)} className="rounded p-1 text-slate-400 hover:bg-slate-100 md:hidden">
            <IconClose className="h-4 w-4" />
          </button>
        </div>
        <button
          onClick={startNewConversation}
          className="mx-3 mt-3 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          style={{ background: "linear-gradient(135deg, #4F46E5, #2563EB)" }}
        >
          <IconPlus className="h-4 w-4" />
          Cuộc trò chuyện mới
        </button>

        {isCLevel && (
          <button
            onClick={openAuditDashboard}
            className="mx-3 mt-2 flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-2 text-left text-sm font-semibold text-indigo-900 shadow-sm ring-1 ring-inset ring-indigo-200 transition hover:bg-indigo-100"
          >
            <IconChart className="h-4 w-4 shrink-0 text-indigo-600" />
            <span className="flex-1">Audit Log & Chi phí AI</span>
            <span className="status-dot-live h-2 w-2 shrink-0 rounded-full bg-emerald-500" title="Dữ liệu realtime" />
          </button>
        )}
        {(isCLevel || userInfo?.role === "regional_director") && sessionOwners.length > 1 && (
          <div className="mx-3 mt-3">
            <select
              value={effectiveOwnerFilter}
              onChange={(e) => setOwnerFilter(e.target.value)}
              title="Lọc lịch sử trò chuyện theo người dùng"
              className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs text-slate-700 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            >
              <option value="all">👥 Tất cả người dùng ({sessions.length})</option>
              {sessionOwners.map((o) => (
                <option key={o.username} value={o.username}>
                  {o.label} ({o.count})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="custom-scroll flex-1 overflow-y-auto px-2 py-3">
          {sessions.length === 0 && (
            <p className="px-2 text-xs text-slate-400">Chưa có cuộc trò chuyện nào.</p>
          )}
          {sessions.length > 0 && visibleSessions.length === 0 && (
            <p className="px-2 text-xs text-slate-400">Người này chưa có cuộc trò chuyện nào.</p>
          )}
          {sessionGroups.map((group) => (
            <div key={group.label} className="mb-3">
              <div className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                {group.label}
              </div>
              {group.items.map((s) => (
                <div
                  key={s.session_id}
                  onClick={() => switchToSession(s.session_id)}
                  className={`group mb-1 flex cursor-pointer items-center justify-between gap-1 rounded-lg px-3 py-2 text-sm transition ${
                    s.session_id === sessionId ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="fade-truncate">{s.title || "Cuộc trò chuyện mới"}</div>
                    <div className="fade-truncate text-xs text-slate-400">
                      {formatRelativeTime(s.updated_at)}
                      {isCLevel && s.owner_username !== userInfo?.username
                        ? ` · ${s.owner_name || s.owner_username}`
                        : ""}
                    </div>
                  </div>
                  {s.owner_username === userInfo?.username && (
                    <button
                      onClick={(e) => deleteSession(s.session_id, e)}
                      className="hidden shrink-0 rounded p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-500 group-hover:block"
                      title="Xóa cuộc trò chuyện"
                    >
                      <IconTrash className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
      <header className="relative z-10 border-b border-slate-800/80 bg-slate-900/95 backdrop-blur-md px-4 sm:px-8 py-3 text-white shadow-lg">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4">
          {/* Left Title & Logo */}
          <div className="flex items-center gap-3.5">
            <button
              onClick={() => setSidebarOpen(true)}
              title="Lịch sử trò chuyện"
              className="rounded-lg p-2 text-slate-300 hover:bg-slate-800 md:hidden"
            >
              <IconMenu className="h-5 w-5" />
            </button>
            <div className="bg-white/95 p-1.5 rounded-xl shadow-md border border-white/20">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/namha-logo.png" alt="NAMHA PHARMA" className="h-8 w-auto object-contain" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-extrabold tracking-wider uppercase text-emerald-400">DƯỢC NAM HÀ</span>
                <span className="inline-flex items-center rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-sm">
                  AI Analyst
                </span>
              </div>
              <h1 className="text-sm sm:text-base font-bold text-slate-100 leading-tight">Trợ lý Phân tích Dữ liệu Kinh doanh</h1>
            </div>
          </div>

          {/* Right User Actions & Badge */}
          <div className="flex items-center gap-2 sm:gap-3">
            {userInfo && (
              <>
                {isCLevel && (
                  <button
                    onClick={() => setAdminUsersOpen(true)}
                    className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-emerald-300 bg-emerald-950/60 border border-emerald-500/40 hover:bg-emerald-900/80 transition shadow-sm"
                    title="Mở Quản lý & Phê duyệt Tài khoản Nhân viên"
                  >
                    <IconUsers className="h-4 w-4" />
                    <span className="hidden md:inline">Quản lý Tài khoản</span>
                  </button>
                )}
                {isCLevel && (
                  <button
                    onClick={openAuditDashboard}
                    className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-amber-300 bg-amber-950/60 border border-amber-500/40 hover:bg-amber-900/80 transition shadow-sm"
                    title="Mở Dashboard Audit Log & Chi phí AI toàn công ty"
                  >
                    <IconChart className="h-4 w-4" />
                    <span className="hidden md:inline">Audit Log & Chi phí AI</span>
                  </button>
                )}
                <button
                  onClick={() => { setPwdChangeMsg(null); setChangePwdOpen(true); }}
                  className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-slate-200 bg-slate-800 border border-slate-700 hover:bg-slate-700 transition shadow-sm"
                  title="Đổi mật khẩu tài khoản"
                >
                  🔑 <span className="hidden sm:inline">Đổi MK</span>
                </button>

                {/* User Info Badge */}
                <div className="hidden sm:flex items-center gap-2.5 bg-slate-800/80 border border-slate-700/80 rounded-xl px-3 py-1.5">
                  <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 text-white font-bold text-xs flex items-center justify-center shadow">
                    {(userInfo.name || userInfo.username).charAt(0).toUpperCase()}
                  </div>
                  <div className="flex flex-col text-left">
                    <span className="text-xs font-bold text-slate-100 max-w-[120px] truncate">{userInfo.name || userInfo.username}</span>
                    <span className="text-[10px] font-semibold text-emerald-400">
                      {ROLE_LABELS[userInfo.role] || userInfo.role}
                      {userInfo.scope_value ? ` · ${userInfo.scope_value}` : ""}
                    </span>
                  </div>
                </div>
              </>
            )}

            <button
              onClick={handleLogout}
              title="Đăng xuất"
              className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-rose-300 bg-rose-950/50 border border-rose-500/30 hover:bg-rose-900/70 transition"
            >
              <IconLogout className="h-4 w-4" />
              <span className="hidden lg:inline">Đăng xuất</span>
            </button>
          </div>
        </div>
      </header>

      {/* Banner Cảnh Báo Tài Khoản Pending */}
      {userInfo?.status === "pending" && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2.5 text-xs text-amber-800 flex items-center justify-between backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <span className="text-base">⏳</span>
            <div>
              <strong className="font-bold">Tài khoản đang ở trạng thái CHỜ DUYỆT:</strong> Quản trị viên C-Level chưa phê duyệt và gán phân quyền. Mọi yêu cầu truy vấn dữ liệu báo cáo sẽ bị tạm từ chối.
            </div>
          </div>
          <button
            onClick={() => { setPwdChangeMsg(null); setChangePwdOpen(true); }}
            className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded font-semibold text-xs shadow-sm transition"
          >
            🔑 Đổi mật khẩu
          </button>
        </div>
      )}

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-hidden px-4">
        <div className="flex-1 overflow-y-auto py-6">
          {historyLoaded && messages.length === 0 && (
            <div className="mt-8">
              <p className="mb-3 text-sm text-slate-500">Thử hỏi một trong các câu sau:</p>
              <div className="flex flex-wrap gap-2">
                {(isCLevel ? SAMPLE_QUESTIONS_CLEVEL : SAMPLE_QUESTIONS_COMMON).map((q) => (
                  <button
                    key={q}
                    onClick={() => sendQuestion(q)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm shadow-sm transition ${
                      q.includes("chi phí AI")
                        ? "border-amber-300 bg-amber-50 text-amber-900 hover:border-amber-400 hover:bg-amber-100 font-medium"
                        : "border-slate-300 bg-white text-slate-700 hover:border-indigo-400 hover:text-indigo-600"
                    }`}
                  >
                    <span aria-hidden="true">{chipIcon(q)}</span>
                    {q}
                  </button>
                ))}
              </div>
              <p className="mt-4 text-xs text-slate-400">
                Mẹo: bạn có thể hỏi tiếp câu liên quan (vd &quot;còn tháng trước thì sao?&quot;) mà
                không cần nhắc lại — trợ lý sẽ nhớ ngữ cảnh trong cuộc trò chuyện này.
              </p>
            </div>
          )}

          <MessageList messages={messages} loading={loading} bottomRef={bottomRef} />
        </div>

        {/* Banner "Danh cho C-Level" da bo (29/07/2026): loi vao Dashboard Audit Log da co san o 2 cho
            (nut tren header + muc trong sidebar), banner thu 3 nam ngay tren o nhap chi lam chat khung
            chat va lap lai cung mot hanh dong. */}
        <form onSubmit={handleSubmit} className="pb-4 pt-2">
          <div className="input-floating flex items-center gap-2 rounded-full border border-slate-200 px-2 py-2 shadow-lg shadow-slate-900/5">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Hỏi về doanh thu, công nợ, KPI, tồn kho..."
              className="flex-1 bg-transparent px-3 py-1.5 text-sm outline-none placeholder:text-slate-400"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              title="Gửi"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white shadow-sm transition hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
              style={{ background: "linear-gradient(135deg, #4F46E5, #2563EB)" }}
            >
              <IconSend className="h-4 w-4" />
            </button>
          </div>
        </form>
      </main>
      </div>

      {/* AUDIT LOG & COST DASHBOARD MODAL FOR C-LEVEL */}
      {auditModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="flex flex-col w-full max-w-5xl max-h-[90vh] bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between bg-[var(--brand-navy)] px-6 py-4 text-white">
              <div className="flex items-center gap-3">
                <span className="glow-indigo flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-200">
                  <IconChart className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-bold">Dashboard Audit Log & Chi phí AI Toàn Công ty</h2>
                  <p className="text-xs text-slate-300">Dành riêng cho Ban Điều Hành (C-Level) · Tra cứu trực tiếp dữ liệu realtime</p>
                </div>
              </div>
              <button
                onClick={() => setAuditModalOpen(false)}
                className="btn-glass rounded-full p-2 text-slate-300 transition hover:text-white"
              >
                <IconClose className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Controls Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-100 border-b border-slate-200 px-6 py-3">
              <div className="flex items-center gap-3">
                {/* Time Range Selector */}
                <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                  <span>Khoảng thời gian:</span>
                  <select
                    value={auditDays}
                    onChange={(e) => {
                      const val = Number(e.target.value);
                      setAuditDays(val);
                      fetchAuditData(val, auditUserFilter);
                    }}
                    className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  >
                    <option value={7}>7 ngày gần nhất</option>
                    <option value={30}>30 ngày gần nhất</option>
                    <option value={90}>90 ngày gần nhất</option>
                  </select>
                </div>

                {/* User Filter Dropdown */}
                <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                  <span>Người dùng:</span>
                  <select
                    value={auditUserFilter}
                    onChange={(e) => {
                      const val = e.target.value;
                      setAuditUserFilter(val);
                      fetchAuditData(auditDays, val);
                    }}
                    className="max-w-[160px] truncate rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  >
                    <option value="all">Tất cả người dùng</option>
                    {auditData?.user_breakdown.map((u) => (
                      <option key={u.username} value={u.username}>
                        {u.user_name} ({u.username})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Refresh & Tabs */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchAuditData(auditDays, auditUserFilter)}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                  disabled={auditLoading}
                >
                  <IconRefresh className={`h-3.5 w-3.5 ${auditLoading ? "animate-spin" : ""}`} />
                  {auditLoading ? "Đang tải..." : "Làm mới"}
                </button>
                {/* Segmented Control (Pill Switcher) */}
                <div className="flex rounded-full bg-slate-200/70 p-1 text-xs">
                  <button
                    onClick={() => setAuditActiveTab("users")}
                    className={`rounded-full px-3.5 py-1.5 font-medium transition ${
                      auditActiveTab === "users" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    👥 Theo Người Dùng
                  </button>
                  <button
                    onClick={() => setAuditActiveTab("weekly")}
                    className={`rounded-full px-3.5 py-1.5 font-medium transition ${
                      auditActiveTab === "weekly" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    📅 Chi Phí Theo Tuần
                  </button>
                  <button
                    onClick={() => setAuditActiveTab("logs")}
                    className={`rounded-full px-3.5 py-1.5 font-medium transition ${
                      auditActiveTab === "logs" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    📝 Nhật Ký Truy Vấn
                  </button>
                </div>
              </div>
            </div>

            {/* Modal Content Body */}
            <div className="custom-scroll flex-1 overflow-y-auto p-6">
              {auditLoading && !auditData ? (
                <div className="flex h-64 items-center justify-center text-sm text-slate-400">
                  Đang tải dữ liệu Audit Log & Chi phí AI...
                </div>
              ) : auditData ? (
                <div className="flex flex-col gap-6">
                  {/* Summary Metric Cards */}
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    {/* Card 1: Tổng Chi Phí AI — Gradient Amber Gold */}
                    <div
                      className="rounded-xl p-4 text-white shadow-sm"
                      style={{ background: "linear-gradient(135deg, #F59E0B, #D97706)" }}
                    >
                      <div className="flex items-center gap-1.5 text-xs font-medium text-amber-50">
                        <IconCoin className="h-3.5 w-3.5" />
                        Tổng Chi Phí AI
                      </div>
                      <div className="mt-1 text-lg font-bold tabular-nums">
                        {auditData.summary.total_cost_vnd.toLocaleString("vi-VN")} đ
                      </div>
                      <div className="text-[11px] tabular-nums text-amber-50/90">
                        ~ ${auditData.summary.total_cost_usd.toFixed(4)} USD
                      </div>
                      {/* Ty gia HIEN THI phai la ty gia BACKEND DA THUC SU DUNG de quy doi, suy nguoc
                          tu chinh du lieu tra ve - khong duoc lay hang so cua frontend. Hai ben co the
                          lech nhau khi frontend da deploy con backend tren may 24 thi chua, va khi do
                          ghi hang so frontend len the la noi sai ve so tien dang hien ngay ben tren. */}
                      {(() => {
                        const usd = auditData.summary.total_cost_usd;
                        const effectiveRate = usd > 0 ? auditData.summary.total_cost_vnd / usd : USD_TO_VND_RATE;
                        const isStale = Math.abs(effectiveRate - USD_TO_VND_RATE) > 1;
                        return (
                          <div
                            className="mt-1.5 inline-flex items-center rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-amber-50"
                            title={isStale ? `Máy chủ đang dùng tỷ giá cũ. Bản mới nhất: ${USD_TO_VND_RATE.toLocaleString("vi-VN")} đ` : undefined}
                          >
                            Quy đổi 1 USD = {Math.round(effectiveRate).toLocaleString("vi-VN")} đ
                            {isStale && " ⚠️"}
                          </div>
                        );
                      })()}
                      {auditData.summary.unattributed_cost_usd > 0 && (
                        <div className="mt-1 text-[10px] leading-tight text-amber-50/80">
                          Trong đó{" "}
                          {(
                            auditData.summary.unattributed_cost_usd *
                            (auditData.summary.total_cost_usd > 0
                              ? auditData.summary.total_cost_vnd / auditData.summary.total_cost_usd
                              : USD_TO_VND_RATE)
                          ).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} đ
                          chưa quy được cho người dùng cụ thể
                        </div>
                      )}
                    </div>

                    {/* Card 2: Tổng Token — thanh phân rã Input/Output/Cache */}
                    <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 shadow-sm">
                      <div className="text-xs font-medium text-blue-700">Tổng Token Tiêu Tốn</div>
                      <div className="mt-1 text-lg font-bold tabular-nums text-blue-900">
                        {auditData.summary.grand_total_tokens.toLocaleString()}
                      </div>
                      {(() => {
                        const tIn = auditData.summary.total_input_tokens;
                        const tOut = auditData.summary.total_output_tokens;
                        const tCache = auditData.summary.total_cache_tokens;
                        const total = tIn + tOut + tCache;
                        const pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);
                        return (
                          <div className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-blue-100">
                            <div style={{ width: `${pct(tIn)}%` }} className="bg-blue-500" title={`Input: ${tIn.toLocaleString()}`} />
                            <div style={{ width: `${pct(tOut)}%` }} className="bg-indigo-500" title={`Output: ${tOut.toLocaleString()}`} />
                            {tCache > 0 && (
                              <div style={{ width: `${pct(tCache)}%` }} className="bg-sky-300" title={`Cache: ${tCache.toLocaleString()}`} />
                            )}
                          </div>
                        );
                      })()}
                      <div className="mt-1 flex flex-wrap gap-x-2 text-[11px] text-blue-600">
                        <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500" /> In {auditData.summary.total_input_tokens.toLocaleString()}</span>
                        <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-500" /> Out {auditData.summary.total_output_tokens.toLocaleString()}</span>
                        {auditData.summary.total_cache_tokens > 0 && (
                          <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-sky-300" /> Cache {auditData.summary.total_cache_tokens.toLocaleString()}</span>
                        )}
                      </div>
                    </div>

                    {/* Card 3: Tổng Lượt Truy Vấn */}
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 shadow-sm">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                        <IconSearch className="h-3.5 w-3.5" />
                        Tổng Lượt Truy Vấn
                      </div>
                      <div className="mt-1 text-lg font-bold tabular-nums text-emerald-900">
                        {auditData.summary.total_queries.toLocaleString()} lượt
                      </div>
                      <div className="text-[11px] tabular-nums text-emerald-600">
                        Trong {auditData.summary.days} ngày · trung bình {(auditData.summary.total_queries / Math.max(1, auditData.summary.days)).toFixed(1)} lượt/ngày
                      </div>
                    </div>

                    {/* Card 4: Người Dùng Hoạt Động */}
                    <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-4 shadow-sm">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-purple-700">
                        <IconUsers className="h-3.5 w-3.5" />
                        Người Dùng Hoạt Động
                      </div>
                      <div className="mt-1 text-lg font-bold tabular-nums text-purple-900">
                        {auditData.summary.unique_users_count} người
                      </div>
                      <div className="text-[11px] text-purple-600">
                        Đang hoạt động trên hệ thống
                      </div>
                    </div>
                  </div>

                  {/* TAB 1: USER BREAKDOWN TABLE */}
                  {auditActiveTab === "users" && (() => {
                    // "Tieu thu cao nhat" chi xet NGUOI DUNG THAT - dong "(chua quy duoc)" khong phai
                    // mot nguoi, truoc day no thuong lon nhat bang nen bi danh dau nham.
                    const realUsers = auditData.user_breakdown.filter((u) => !u.is_unattributed);
                    const maxCost = Math.max(0, ...realUsers.map((u) => u.cost_usd));
                    const hasUnattributed = auditData.user_breakdown.some((u) => u.is_unattributed);
                    const hasZeroCostUser = realUsers.some((u) => u.query_count > 0 && u.cost_usd === 0);
                    return (
                      <div className="flex flex-col gap-3">
                        <h3 className="text-sm font-bold text-slate-800">
                          📊 Bảng Thống Kê Token & Chi Phí Theo Người Dùng
                        </h3>
                        {(hasUnattributed || hasZeroCostUser) && (
                          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-900">
                            <span className="font-semibold">Vì sao có dòng 0 đồng và dòng &ldquo;chưa quy được&rdquo;:</span>{" "}
                            sổ chi phí chỉ bắt đầu ghi kèm tên tài khoản từ 29/07/2026. Những lượt hỏi
                            trước mốc đó vẫn được đếm ở cột &ldquo;Số câu hỏi&rdquo; nhưng không nối
                            ngược được sang tiền, nên phần tiền của chúng dồn vào dòng cuối bảng.
                            Tổng tiền toàn công ty vẫn đúng.
                          </div>
                        )}
                        <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-200 shadow-sm">
                          <table className="min-w-full text-xs tabular-nums">
                            <thead className="sticky top-0 z-10 bg-[#F1F5F9] text-slate-700 font-semibold shadow-[0_1px_0_0_theme(colors.slate.200)]">
                              <tr>
                                <th className="px-4 py-3 text-left">Người Dùng</th>
                                <th className="px-4 py-3 text-center">Tài Khoản</th>
                                <th className="px-4 py-3 text-right">Số Câu Hỏi</th>
                                <th className="px-4 py-3 text-right">Input</th>
                                <th className="px-4 py-3 text-right">Output</th>
                                <th className="px-4 py-3 text-right">Cache</th>
                                <th className="px-4 py-3 text-right">Tổng Tokens</th>
                                <th className="px-4 py-3 text-right">Chi Phí (USD)</th>
                                <th className="px-4 py-3 text-right font-bold text-amber-700">Chi Phí (VNĐ)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 bg-white">
                              {auditData.user_breakdown.map((u) => {
                                const isTop = !u.is_unattributed && maxCost > 0 && u.cost_usd === maxCost;
                                // Ban backend cu chua tra cache_tokens - suy nguoc tu tong de cot Cache
                                // van dung thay vi hien 0.
                                const cacheTokens =
                                  u.cache_tokens ?? Math.max(0, u.total_tokens - u.input_tokens - u.output_tokens);
                                return (
                                  <tr
                                    key={u.username}
                                    className={`transition ${
                                      u.is_unattributed
                                        ? "bg-slate-50 italic text-slate-500 hover:bg-slate-100"
                                        : isTop
                                        ? "bg-amber-50/60 hover:bg-amber-50"
                                        : "hover:bg-slate-50"
                                    }`}
                                  >
                                    <td className="px-4 py-3 font-medium text-slate-900">
                                      <span className="inline-flex items-center gap-1.5">
                                        {isTop && <span title="Mức tiêu thụ cao nhất trong kỳ">🔥</span>}
                                        {u.user_name}
                                      </span>
                                    </td>
                                    <td className="px-4 py-3 text-center text-slate-500 font-mono">{u.username}</td>
                                    <td className="px-4 py-3 text-right text-slate-700 font-semibold">{u.query_count}</td>
                                    <td className="px-4 py-3 text-right text-slate-600">{u.input_tokens.toLocaleString()}</td>
                                    <td className="px-4 py-3 text-right text-slate-600">{u.output_tokens.toLocaleString()}</td>
                                    <td className="px-4 py-3 text-right text-slate-600">{cacheTokens.toLocaleString()}</td>
                                    <td className="px-4 py-3 text-right font-medium text-slate-800">{u.total_tokens.toLocaleString()}</td>
                                    <td className="px-4 py-3 text-right text-slate-600">${u.cost_usd.toFixed(4)}</td>
                                    <td className="px-4 py-3 text-right font-bold text-amber-700">
                                      {u.cost_vnd.toLocaleString("vi-VN")} đ
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })()}

                  {/* TAB 2: WEEKLY TOKEN COST DASHBOARD */}
                  {auditActiveTab === "weekly" && (
                    <div className="flex flex-col gap-4">
                      {/* Week Navigation Header */}
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50/80 via-purple-50/50 to-blue-50/80 p-3.5 shadow-sm">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setWeeklyOffset((prev) => prev - 1)}
                            className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100 hover:text-indigo-600"
                          >
                            ◀️ Tuần trước
                          </button>
                          <button
                            onClick={() => setWeeklyOffset(0)}
                            disabled={weeklyOffset === 0}
                            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold shadow-sm transition ${
                              weeklyOffset === 0
                                ? "border-slate-200 bg-slate-100 text-slate-400 cursor-not-allowed"
                                : "border-indigo-300 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                            }`}
                          >
                            🔄 Tuần này
                          </button>
                          <button
                            onClick={() => setWeeklyOffset((prev) => prev + 1)}
                            disabled={weeklyOffset >= 0}
                            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold shadow-sm transition ${
                              weeklyOffset >= 0
                                ? "border-slate-200 bg-slate-100 text-slate-400 cursor-not-allowed"
                                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100 hover:text-indigo-600"
                            }`}
                          >
                            Tuần sau ▶️
                          </button>
                        </div>
                        <div className="text-right">
                          <div className="flex items-center gap-2 text-xs sm:text-sm font-bold text-slate-800">
                            <span>📅 Tuần: {weeklyData?.week_label || "Đang tải..."}</span>
                            {weeklyData?.is_current_week && (
                              <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800 border border-emerald-300 shadow-sm">
                                Tuần hiện tại
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Weekly Summary Cards */}
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3 shadow-sm">
                          <div className="text-[11px] font-medium text-blue-700">🪙 Tổng Tokens Tuần</div>
                          <div className="mt-1 text-base font-bold tabular-nums text-blue-900">
                            {(weeklyData?.total_tokens || 0).toLocaleString()}
                          </div>
                        </div>
                        <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 shadow-sm">
                          <div className="text-[11px] font-medium text-amber-700">🇻🇳 Tổng VNĐ Tuần</div>
                          <div className="mt-1 text-base font-bold tabular-nums text-amber-900">
                            {(weeklyData?.total_cost_vnd || 0).toLocaleString("vi-VN")} đ
                          </div>
                        </div>
                        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 shadow-sm">
                          <div className="text-[11px] font-medium text-emerald-700">💵 Chi Phí (USD)</div>
                          <div className="mt-1 text-base font-bold tabular-nums text-emerald-900">
                            ${(weeklyData?.total_cost_usd || 0).toFixed(4)}
                          </div>
                        </div>
                        <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-3 shadow-sm">
                          <div className="text-[11px] font-medium text-purple-700">💬 Số Lượt Truy Vấn</div>
                          <div className="mt-1 text-base font-bold tabular-nums text-purple-900">
                            {(weeklyData?.total_queries || 0).toLocaleString()} lượt
                          </div>
                        </div>
                      </div>

                      {/* 7-Day Breakdown Grid Cards */}
                      <div>
                        <h4 className="mb-2 text-xs font-bold text-slate-700">📆 Chi Phí & Tokens Chi Tiết Theo Thứ Trong Tuần</h4>
                        {weeklyLoading && !weeklyData ? (
                          <div className="flex h-32 items-center justify-center text-xs text-slate-400">
                            Đang tải dữ liệu tuần...
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-7">
                            {weeklyData?.daily_breakdown.map((day) => {
                              const maxCost = Math.max(1, ...(weeklyData.daily_breakdown.map((d) => d.cost_vnd) || [1]));
                              const barPct = Math.min(100, Math.round((day.cost_vnd / maxCost) * 100));
                              return (
                                <div
                                  key={day.day_index}
                                  className={`flex flex-col justify-between rounded-xl border p-3 transition shadow-sm ${
                                    day.is_today
                                      ? "border-indigo-400 bg-gradient-to-b from-indigo-50/90 to-white ring-2 ring-indigo-300"
                                      : day.query_count > 0
                                      ? "border-slate-200 bg-white hover:border-slate-300"
                                      : "border-slate-100 bg-slate-50/50 opacity-70"
                                  }`}
                                >
                                  <div>
                                    <div className="flex items-center justify-between border-b border-slate-100 pb-1.5">
                                      <span className="text-xs font-bold text-slate-800">{day.day_name}</span>
                                      <span className={`text-[10px] font-semibold ${day.is_today ? "text-indigo-600 font-bold" : "text-slate-400"}`}>
                                        {day.display_date} {day.is_today && "⭐"}
                                      </span>
                                    </div>
                                    <div className="mt-2 text-sm font-bold tabular-nums text-amber-700">
                                      {day.cost_vnd.toLocaleString("vi-VN")} đ
                                    </div>
                                    <div className="text-[11px] tabular-nums text-slate-500">
                                      {day.total_tokens.toLocaleString()} tokens
                                    </div>
                                    <div className="text-[10px] text-slate-400">
                                      {day.query_count} lượt hỏi
                                    </div>
                                  </div>
                                  <div className="mt-2.5">
                                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                                      <div
                                        style={{ width: `${barPct}%` }}
                                        className={`h-full rounded-full transition-all duration-300 ${
                                          day.is_today ? "bg-indigo-600" : "bg-amber-500"
                                        }`}
                                      />
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      {/* Weekly User Breakdown Table */}
                      <div className="flex flex-col gap-2">
                        <h4 className="text-xs font-bold text-slate-700">👥 Thống Kê Theo Tài Khoản Trong Tuần Này</h4>
                        <div className="max-h-48 overflow-auto rounded-xl border border-slate-200 shadow-sm">
                          <table className="min-w-full text-xs tabular-nums">
                            <thead className="sticky top-0 bg-slate-100 text-slate-700 font-semibold shadow-[0_1px_0_0_theme(colors.slate.200)]">
                              <tr>
                                <th className="px-3 py-2 text-left">Người Dùng</th>
                                <th className="px-3 py-2 text-center">Tài Khoản</th>
                                <th className="px-3 py-2 text-right">Số Câu Hỏi</th>
                                <th className="px-3 py-2 text-right">Tổng Tokens</th>
                                <th className="px-3 py-2 text-right font-bold text-amber-700">Chi Phí (VNĐ)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 bg-white">
                              {weeklyData?.user_breakdown.map((u) => (
                                <tr key={u.username} className="hover:bg-slate-50">
                                  <td className="px-3 py-2 font-medium text-slate-900">{u.user_name}</td>
                                  <td className="px-3 py-2 text-center text-slate-500 font-mono">{u.username}</td>
                                  <td className="px-3 py-2 text-right font-semibold text-slate-700">{u.query_count}</td>
                                  <td className="px-3 py-2 text-right text-slate-600">{u.total_tokens.toLocaleString()}</td>
                                  <td className="px-3 py-2 text-right font-bold text-amber-700">{u.cost_vnd.toLocaleString("vi-VN")} đ</td>
                                </tr>
                              ))}
                              {(!weeklyData || weeklyData.user_breakdown.length === 0) && (
                                <tr>
                                  <td colSpan={5} className="px-3 py-4 text-center text-slate-400 italic">
                                    Chưa có dữ liệu truy vấn trong tuần này.
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 2: DETAILED QUERY AUDIT LOGS TABLE */}
                  {auditActiveTab === "logs" && (
                    <div className="flex flex-col gap-3">
                      <h3 className="text-sm font-bold text-slate-800">
                        📝 Nhật Ký Truy Vấn Chi Tiết ({auditData.logs.length} dòng gần nhất)
                      </h3>
                      <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-200 shadow-sm">
                        <table className="min-w-full text-xs tabular-nums">
                          <thead className="sticky top-0 z-10 bg-[#F1F5F9] text-slate-700 font-semibold shadow-[0_1px_0_0_theme(colors.slate.200)]">
                            <tr>
                              <th className="px-4 py-3 text-left">Thời Gian</th>
                              <th className="px-4 py-3 text-left">Người Dùng</th>
                              <th className="px-4 py-3 text-left">Nội Dung Câu Hỏi</th>
                              <th className="px-4 py-3 text-right">Input Tokens<div className="font-normal text-[10px] text-slate-400">(cả phiên)</div></th>
                              <th className="px-4 py-3 text-right">Output Tokens<div className="font-normal text-[10px] text-slate-400">(cả phiên)</div></th>
                              <th className="px-4 py-3 text-right">Chi Phí (VNĐ)<div className="font-normal text-[10px] text-slate-400">(cả phiên)</div></th>
                              <th className="px-4 py-3 text-center">Thời Gian Chạy</th>
                              <th className="px-4 py-3 text-center">Chi Tiết SQL</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {auditData.logs.map((log, idx) => (
                              <tr key={idx} className="transition hover:bg-slate-50">
                                <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                                  {log.ts ? log.ts.replace("T", " ").slice(0, 19) : "—"}
                                </td>
                                <td className="px-4 py-3 font-medium text-slate-900 whitespace-nowrap">
                                  {log.user_name}
                                </td>
                                <td className="px-4 py-3 text-slate-800 font-normal max-w-xs truncate" title={log.question}>
                                  {log.question}
                                </td>
                                <td className="px-4 py-3 text-right text-slate-600">{log.session_input_tokens.toLocaleString()}</td>
                                <td className="px-4 py-3 text-right text-slate-600">{log.session_output_tokens.toLocaleString()}</td>
                                <td className="px-4 py-3 text-right font-semibold text-amber-700">
                                  {log.session_cost_vnd.toLocaleString("vi-VN")} đ
                                </td>
                                <td className="px-4 py-3 text-center text-slate-500 whitespace-nowrap">
                                  {log.duration_ms ? `${log.duration_ms} ms` : "—"}
                                </td>
                                <td className="px-4 py-3 text-center">
                                  {log.sql ? (
                                    <details className="inline-block text-left">
                                      <summary className="cursor-pointer font-medium text-indigo-600 hover:underline">
                                        Xem SQL
                                      </summary>
                                      <pre className="mt-2 max-w-md overflow-x-auto rounded bg-slate-900 p-3 text-[11px] text-slate-100">
                                        {log.sql}
                                      </pre>
                                    </details>
                                  ) : (
                                    <span className="text-slate-400">—</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex h-64 items-center justify-center text-sm text-slate-400">
                  Không tìm thấy dữ liệu Audit Log.
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3 text-xs text-slate-500">
              <span>
                * Chi phí quy đổi tự động theo tỷ giá{" "}
                {auditData && auditData.summary.total_cost_usd > 0
                  ? Math.round(auditData.summary.total_cost_vnd / auditData.summary.total_cost_usd).toLocaleString("vi-VN")
                  : USD_TO_VND_RATE.toLocaleString("vi-VN")}{" "}
                đ/USD và bảng giá Anthropic API chính thức. Tổng lấy thẳng từ sổ chi phí nên luôn đúng
                kể cả khi chưa quy được từng lượt về người dùng cụ thể.
              </span>
              <button
                onClick={() => setAuditModalOpen(false)}
                className="rounded-lg bg-[var(--brand-navy)] px-4 py-2 text-xs font-medium text-white transition hover:bg-slate-800"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Admin Users Panel */}
      {adminUsersOpen && authToken && (
        <AdminUsersPanel authToken={authToken} onClose={() => setAdminUsersOpen(false)} />
      )}

      {/* Modal Đổi Mật Khẩu */}
      {changePwdOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200">
            <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
              <h3 className="font-bold text-sm">🔑 Đổi Mật Khẩu Tài Khoản</h3>
              <button onClick={() => setChangePwdOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setPwdChangeSubmitting(true);
                setPwdChangeMsg(null);
                try {
                  const res = await fetch("/api/auth/change-password", {
                    method: "POST",
                    headers: authHeaders(authToken),
                    body: JSON.stringify({
                      current_password: currentPwdInput,
                      new_password: newPwdInput,
                    }),
                  });
                  const data = await res.json();
                  if (!res.ok) throw new Error(data.detail || "Đổi mật khẩu thất bại");
                  setPwdChangeMsg({ text: data.message || "Đổi mật khẩu thành công!", type: "success" });
                  setCurrentPwdInput("");
                  setNewPwdInput("");
                } catch (err: any) {
                  setPwdChangeMsg({ text: err.message, type: "error" });
                } finally {
                  setPwdChangeSubmitting(false);
                }
              }}
              className="p-6 space-y-4"
            >
              {pwdChangeMsg && (
                <div
                  className={`p-3 rounded-lg text-xs font-medium ${
                    pwdChangeMsg.type === "success"
                      ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                      : "bg-rose-50 text-rose-800 border border-rose-200"
                  }`}
                >
                  {pwdChangeMsg.text}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Mật khẩu hiện tại</label>
                <input
                  type="password"
                  required
                  value={currentPwdInput}
                  onChange={(e) => setCurrentPwdInput(e.target.value)}
                  className="w-full px-3.5 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-600"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Mật khẩu mới (Tối thiểu 6 ký tự)</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={newPwdInput}
                  onChange={(e) => setNewPwdInput(e.target.value)}
                  className="w-full px-3.5 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-600"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setChangePwdOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={pwdChangeSubmitting}
                  className="px-4 py-2 bg-blue-700 hover:bg-blue-800 text-white rounded-lg text-xs font-semibold shadow disabled:opacity-50"
                >
                  {pwdChangeSubmitting ? "Đang lưu..." : "Cập nhật Mật Khẩu 💾"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
