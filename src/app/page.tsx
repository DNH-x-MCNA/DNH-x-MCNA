"use client";

import { useState, useRef, useEffect, useMemo, memo, FormEvent, ReactNode, RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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

type UserInfo = { username: string; name: string | null; role: string; scope_value: string | null };

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
  total_tokens: number;
  cost_usd: number;
  cost_vnd: number;
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
  c_level: "Ban Điều Hành (toàn công ty)",
  regional_director: "Giám đốc miền",
  qlv: "Quản lý vùng",
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
  th: ({ children }: { children?: ReactNode }) => (
    <th className="px-3 py-2 text-left font-semibold text-slate-600">{children}</th>
  ),
  // Tag mau cho o chi chua dung 1 khoa kenh/vung, can-phai cho o chi chua so/phan tram/tien te - ca
  // hai deu chi ap dung khi getPlainCellText tra ve chuoi thuan (khong co the long ben trong), neu
  // khong khop dieu kien nao thi giu nguyen cach render mac dinh nhu truoc.
  td: ({ children }: { children?: ReactNode }) => {
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
    const numeric = trimmed ? isNumericLikeCell(trimmed) : false;
    return (
      <td className={`px-3 py-2 text-slate-700 ${numeric ? "text-right" : "text-left"}`}>{children}</td>
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
            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
              m.role === "user"
                ? "bg-indigo-600 text-white"
                : m.error
                ? "bg-red-50 text-red-700 border border-red-200"
                : "bg-white text-slate-800 border border-slate-200 shadow-sm"
            }`}
          >
            {m.role === "bot" ? (
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
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
  const [auditActiveTab, setAuditActiveTab] = useState<"users" | "logs">("users");

  // 28/07/2026: CHI dua vao role, KHONG suy quyen tu chuoi username nua (truoc day con nhan
  // username === "c_level" || username === "dnh"). Day la ban sao o tang giao dien cua lo hong R-I
  // vua va o backend: suy quyen tu TEN tai khoan nghia la them tai khoan ten "dnh.marketing" hay
  // "c_level.tro.ly" la tu nhien thay nut xem chi phi toan cong ty. O frontend hau qua nhe hon
  // (chi an/hien nut, quyen that da chan o backend qua scope_role) nhung van phai sua cho nhat quan.
  const isCLevel = Boolean(
    userInfo && (
      userInfo.role?.toLowerCase() === "c_level" ||
      userInfo.role?.toLowerCase() === "admin"
    )
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

  const openAuditDashboard = () => {
    setAuditModalOpen(true);
    fetchAuditData(auditDays, auditUserFilter);
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

  if (!authToken) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 px-4">
        <form
          onSubmit={handleLogin}
          className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
        >
          <div className="mb-6 flex flex-col items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/namha-logo.png" alt="NAMHA PHARMA" className="h-10 w-auto" />
            <h1 className="text-center text-lg font-bold text-slate-900">Đăng nhập AI Analyst</h1>
            <p className="text-center text-xs text-slate-500">Dược Nam Hà · Trợ lý phân tích dữ liệu kinh doanh</p>
          </div>
          <div className="flex flex-col gap-3">
            <input
              type="text"
              placeholder="Tên đăng nhập"
              value={loginUsername}
              onChange={(e) => setLoginUsername(e.target.value)}
              className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
              disabled={loginSubmitting}
              autoFocus
            />
            <input
              type="password"
              placeholder="Mật khẩu"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
              disabled={loginSubmitting}
            />
            {loginError && <p className="text-xs text-red-600">{loginError}</p>}
            <button
              type="submit"
              disabled={loginSubmitting || !loginUsername.trim() || !loginPassword}
              className="mt-1 rounded-lg py-2.5 text-sm font-medium text-white shadow-sm transition hover:shadow-md disabled:cursor-not-allowed disabled:opacity-40"
              style={{ background: "linear-gradient(135deg, #4F46E5, #2563EB)" }}
            >
              {loginSubmitting ? "Đang đăng nhập..." : "Đăng nhập"}
            </button>
          </div>
        </form>
      </div>
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
        {isCLevel && sessionOwners.length > 1 && (
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
      <header className="relative z-10 border-b border-slate-800/60 bg-[var(--brand-navy)] px-6 py-4 text-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              title="Lịch sử trò chuyện"
              className="rounded-lg p-1.5 text-slate-300 hover:bg-white/10 md:hidden"
            >
              <IconMenu className="h-5 w-5" />
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/namha-logo.png" alt="NAMHA PHARMA" className="h-9 w-auto" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold tracking-wide text-slate-300">DƯỢC NAM HÀ</span>
                <span className="glow-indigo inline-flex items-center rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-indigo-200">
                  AI Analyst
                </span>
              </div>
              <h1 className="text-lg font-bold leading-tight sm:text-xl">Trợ lý phân tích dữ liệu kinh doanh</h1>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            {userInfo && (
              <>
                {isCLevel && (
                  <button
                    onClick={openAuditDashboard}
                    className="btn-glass flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold text-amber-200 transition hover:text-amber-100"
                    title="Mở Dashboard Audit Log & Chi phí AI toàn công ty"
                  >
                    <IconChart className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Audit Log & Chi phí AI</span>
                  </button>
                )}
                <div className="hidden flex-col items-end gap-1 sm:flex">
                  <span className="text-xs font-medium text-white">{userInfo.name || userInfo.username}</span>
                  <span className="badge-metallic inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold text-indigo-100 shadow-sm">
                    {ROLE_LABELS[userInfo.role] || userInfo.role}
                    {userInfo.scope_value ? ` · ${userInfo.scope_value}` : ""}
                  </span>
                </div>
              </>
            )}
            <button
              onClick={handleLogout}
              title="Đăng xuất"
              className="btn-glass flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs text-slate-200 transition hover:text-red-300"
            >
              <IconLogout className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Đăng xuất</span>
            </button>
          </div>
        </div>
      </header>

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
                      <div className="mt-1.5 inline-flex items-center rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-amber-50">
                        Quy đổi 1 USD = {USD_TO_VND_RATE.toLocaleString("vi-VN")} đ
                      </div>
                      {auditData.summary.unattributed_cost_usd > 0 && (
                        <div className="mt-1 text-[10px] leading-tight text-amber-50/80">
                          Trong đó {(auditData.summary.unattributed_cost_usd * USD_TO_VND_RATE).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} đ
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
                    const maxCost = Math.max(0, ...auditData.user_breakdown.map((u) => u.cost_usd));
                    return (
                      <div className="flex flex-col gap-3">
                        <h3 className="text-sm font-bold text-slate-800">
                          📊 Bảng Thống Kê Token & Chi Phí Theo Người Dùng
                        </h3>
                        <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-200 shadow-sm">
                          <table className="min-w-full text-xs tabular-nums">
                            <thead className="sticky top-0 z-10 bg-[#F1F5F9] text-slate-700 font-semibold shadow-[0_1px_0_0_theme(colors.slate.200)]">
                              <tr>
                                <th className="px-4 py-3 text-left">Người Dùng</th>
                                <th className="px-4 py-3 text-center">Tài Khoản</th>
                                <th className="px-4 py-3 text-right">Số Câu Hỏi</th>
                                <th className="px-4 py-3 text-right">Input Tokens</th>
                                <th className="px-4 py-3 text-right">Output Tokens</th>
                                <th className="px-4 py-3 text-right">Tổng Tokens</th>
                                <th className="px-4 py-3 text-right">Chi Phí (USD)</th>
                                <th className="px-4 py-3 text-right font-bold text-amber-700">Chi Phí (VNĐ)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 bg-white">
                              {auditData.user_breakdown.map((u) => {
                                const isTop = maxCost > 0 && u.cost_usd === maxCost;
                                return (
                                  <tr key={u.username} className={`transition ${isTop ? "bg-amber-50/60 hover:bg-amber-50" : "hover:bg-slate-50"}`}>
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
              <span>* Chi phí quy đổi tự động theo tỷ giá 1 USD = {USD_TO_VND_RATE.toLocaleString("vi-VN")} VNĐ và bảng giá Anthropic API chính thức.</span>
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

    </div>
  );
}
