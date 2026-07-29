"use client";

import { useState, useRef, useEffect, memo, FormEvent, ReactNode, RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ChatResponse = {
  answer: string;
  sql_used: string[];
  columns: string[] | null;
  rows: unknown[][] | null;
  row_count: number | null;
};

type HistoryMessage = { role: "user" | "assistant"; content: string };

type SessionSummary = {
  session_id: string;
  title: string | null;
  owner_username: string;
  owner_name: string | null;
  created_at: string;
  updated_at: string;
};

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
  total_input_tokens: number;
  total_output_tokens: number;
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
    <div className="mb-2 mt-1 overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => <thead className="bg-slate-100">{children}</thead>,
  tbody: ({ children }: { children?: ReactNode }) => <tbody>{children}</tbody>,
  tr: ({ children }: { children?: ReactNode }) => <tr className="border-t border-slate-100">{children}</tr>,
  th: ({ children }: { children?: ReactNode }) => (
    <th className="px-3 py-2 text-left font-semibold text-slate-600">{children}</th>
  ),
  td: ({ children }: { children?: ReactNode }) => <td className="px-3 py-2 text-slate-700">{children}</td>,
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
                ? "bg-blue-600 text-white"
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

            {m.rows && m.columns && m.rows.length > 0 && (
              <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-100">
                    <tr>
                      {m.columns.map((c) => (
                        <th key={c} className="px-3 py-2 text-left font-semibold text-slate-600">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {m.rows.map((row, ri) => (
                      <tr key={ri} className="border-t border-slate-100">
                        {row.map((cell, ci) => (
                          <td key={ci} className="px-3 py-2 text-slate-700">
                            {cell === null ? "—" : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

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
              className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              disabled={loginSubmitting}
              autoFocus
            />
            <input
              type="password"
              placeholder="Mật khẩu"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              disabled={loginSubmitting}
            />
            {loginError && <p className="text-xs text-red-600">{loginError}</p>}
            <button
              type="submit"
              disabled={loginSubmitting || !loginUsername.trim() || !loginPassword}
              className="mt-1 rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loginSubmitting ? "Đang đăng nhập..." : "Đăng nhập"}
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50">
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
          <button onClick={() => setSidebarOpen(false)} className="text-slate-400 md:hidden">
            ✕
          </button>
        </div>
        <button
          onClick={startNewConversation}
          className="mx-3 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          + Cuộc trò chuyện mới
        </button>

        {isCLevel && (
          <button
            onClick={openAuditDashboard}
            className="mx-3 mt-2 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-left text-sm font-semibold text-amber-900 shadow-sm transition hover:bg-amber-100"
          >
            <span>📊</span>
            <span>Audit Log & Chi phí AI</span>
          </button>
        )}
        <div className="flex-1 overflow-y-auto px-2 py-3">
          {sessions.length === 0 && (
            <p className="px-2 text-xs text-slate-400">Chưa có cuộc trò chuyện nào.</p>
          )}
          {sessions.map((s) => (
            <div
              key={s.session_id}
              onClick={() => switchToSession(s.session_id)}
              className={`group mb-1 flex cursor-pointer items-center justify-between gap-1 rounded-lg px-3 py-2 text-sm transition ${
                s.session_id === sessionId ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate">{s.title || "Cuộc trò chuyện mới"}</div>
                <div className="truncate text-xs text-slate-400">
                  {formatRelativeTime(s.updated_at)}
                  {isCLevel && s.owner_username !== userInfo?.username
                    ? ` · ${s.owner_name || s.owner_username}`
                    : ""}
                </div>
              </div>
              {s.owner_username === userInfo?.username && (
                <button
                  onClick={(e) => deleteSession(s.session_id, e)}
                  className="hidden shrink-0 rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 group-hover:block"
                  title="Xóa cuộc trò chuyện"
                >
                  🗑
                </button>
              )}
            </div>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
      <header className="border-b border-slate-200 bg-slate-900 px-6 py-4 text-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              title="Lịch sử trò chuyện"
              className="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 md:hidden"
            >
              ☰
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/namha-logo.png" alt="NAMHA PHARMA" className="h-9 w-auto" />
            <div>
              <div className="text-xs tracking-wide text-blue-300">DƯỢC NAM HÀ · AI ANALYST</div>
              <h1 className="text-xl font-bold">Trợ lý phân tích dữ liệu kinh doanh</h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {userInfo && (
              <>
                {isCLevel && (
                  <button
                    onClick={openAuditDashboard}
                    className="flex items-center gap-1.5 rounded-full border border-amber-500/50 bg-amber-500/20 px-3.5 py-1.5 text-xs font-semibold text-amber-300 shadow-sm transition hover:bg-amber-500/30 hover:text-amber-100 hover:border-amber-400"
                    title="Mở Dashboard Audit Log & Chi phí AI toàn công ty"
                  >
                    <span>📊</span>
                    <span>Audit Log & Chi phí AI</span>
                  </button>
                )}
                <div className="hidden text-right text-xs text-slate-300 sm:block">
                  <div className="font-medium text-white">{userInfo.name || userInfo.username}</div>
                  <div>
                    {ROLE_LABELS[userInfo.role] || userInfo.role}
                    {userInfo.scope_value ? ` · ${userInfo.scope_value}` : ""}
                  </div>
                </div>
              </>
            )}
            <button
              onClick={handleLogout}
              title="Đăng xuất"
              className="rounded-full border border-slate-600 px-4 py-2 text-xs text-slate-200 transition hover:border-red-400 hover:text-red-300"
            >
              Đăng xuất
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
                    className={`rounded-full border px-4 py-2 text-sm transition shadow-sm ${
                      q.includes("chi phí AI")
                        ? "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 hover:border-amber-400 font-medium"
                        : "border-slate-300 bg-white text-slate-700 hover:border-blue-400 hover:text-blue-600"
                    }`}
                  >
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

        {isCLevel && (
          <div className="mb-2 flex items-center justify-between rounded-xl border border-amber-300 bg-amber-50/90 px-4 py-2.5 text-xs font-semibold text-amber-900 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="text-base">📊</span>
              <span>Dành cho C-Level: Xem Dashboard Audit Log & Chi phí AI toàn công ty realtime.</span>
            </div>
            <button
              type="button"
              onClick={openAuditDashboard}
              className="rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-bold text-white shadow hover:bg-amber-700 transition shrink-0"
            >
              Mở Dashboard Audit Log
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-slate-50 py-4">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Hỏi về doanh thu, công nợ, KPI, tồn kho..."
              className="flex-1 rounded-full border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="rounded-full bg-blue-600 px-6 py-3 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Gửi
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
            <div className="flex items-center justify-between bg-slate-900 px-6 py-4 text-white">
              <div className="flex items-center gap-3">
                <span className="text-2xl">📊</span>
                <div>
                  <h2 className="text-lg font-bold">Dashboard Audit Log & Chi phí AI Toàn Công ty</h2>
                  <p className="text-xs text-slate-300">Dành riêng cho Ban Điều Hành (C-Level) · Tra cứu trực tiếp dữ liệu realtime</p>
                </div>
              </div>
              <button
                onClick={() => setAuditModalOpen(false)}
                className="rounded-full p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition"
              >
                ✕
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
                    className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-800 outline-none focus:border-blue-500"
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
                    className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-800 outline-none focus:border-blue-500 max-w-[160px] truncate"
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
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
                  disabled={auditLoading}
                >
                  {auditLoading ? "Đang tải..." : "🔄 Làm mới"}
                </button>
                <div className="flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs">
                  <button
                    onClick={() => setAuditActiveTab("users")}
                    className={`px-3 py-1 rounded-md font-medium transition ${
                      auditActiveTab === "users" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    👥 Theo Người Dùng
                  </button>
                  <button
                    onClick={() => setAuditActiveTab("logs")}
                    className={`px-3 py-1 rounded-md font-medium transition ${
                      auditActiveTab === "logs" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    📝 Nhật Ký Truy Vấn
                  </button>
                </div>
              </div>
            </div>

            {/* Modal Content Body */}
            <div className="flex-1 overflow-y-auto p-6">
              {auditLoading && !auditData ? (
                <div className="flex h-64 items-center justify-center text-sm text-slate-400">
                  Đang tải dữ liệu Audit Log & Chi phí AI...
                </div>
              ) : auditData ? (
                <div className="flex flex-col gap-6">
                  {/* Summary Metric Cards */}
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 shadow-sm">
                      <div className="text-xs font-medium text-amber-700">Tổng Chi Phí AI</div>
                      <div className="mt-1 text-lg font-bold text-amber-900">
                        {auditData.summary.total_cost_vnd.toLocaleString("vi-VN")} đ
                      </div>
                      <div className="text-[11px] text-amber-600">
                        ~ ${auditData.summary.total_cost_usd.toFixed(4)} USD
                      </div>
                    </div>

                    <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 shadow-sm">
                      <div className="text-xs font-medium text-blue-700">Tổng Token Tiêu Tốn</div>
                      <div className="mt-1 text-lg font-bold text-blue-900">
                        {auditData.summary.grand_total_tokens.toLocaleString()}
                      </div>
                      <div className="text-[11px] text-blue-600">
                        In: {auditData.summary.total_input_tokens.toLocaleString()} · Out: {auditData.summary.total_output_tokens.toLocaleString()}
                      </div>
                    </div>

                    <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 shadow-sm">
                      <div className="text-xs font-medium text-emerald-700">Tổng Lượt Truy Vấn</div>
                      <div className="mt-1 text-lg font-bold text-emerald-900">
                        {auditData.summary.total_queries.toLocaleString()} lượt
                      </div>
                      <div className="text-[11px] text-emerald-600">
                        Trong {auditData.summary.days} ngày qua
                      </div>
                    </div>

                    <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-4 shadow-sm">
                      <div className="text-xs font-medium text-purple-700">Người Dùng Hoạt Động</div>
                      <div className="mt-1 text-lg font-bold text-purple-900">
                        {auditData.summary.unique_users_count} người
                      </div>
                      <div className="text-[11px] text-purple-600">
                        Đang hoạt động trên hệ thống
                      </div>
                    </div>
                  </div>

                  {/* TAB 1: USER BREAKDOWN TABLE */}
                  {auditActiveTab === "users" && (
                    <div className="flex flex-col gap-3">
                      <h3 className="text-sm font-bold text-slate-800">
                        📊 Bảng Thống Kê Token & Chi Phí Theo Người Dùng
                      </h3>
                      <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
                        <table className="min-w-full text-xs">
                          <thead className="bg-slate-100 text-slate-700 font-semibold border-b border-slate-200">
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
                            {auditData.user_breakdown.map((u) => (
                              <tr key={u.username} className="hover:bg-slate-50 transition">
                                <td className="px-4 py-3 font-medium text-slate-900">{u.user_name}</td>
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
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* TAB 2: DETAILED QUERY AUDIT LOGS TABLE */}
                  {auditActiveTab === "logs" && (
                    <div className="flex flex-col gap-3">
                      <h3 className="text-sm font-bold text-slate-800">
                        📝 Nhật Ký Truy Vấn Chi Tiết ({auditData.logs.length} dòng gần nhất)
                      </h3>
                      <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
                        <table className="min-w-full text-xs">
                          <thead className="bg-slate-100 text-slate-700 font-semibold border-b border-slate-200">
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
                              <tr key={idx} className="hover:bg-slate-50 transition">
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
                                      <summary className="cursor-pointer font-medium text-blue-600 hover:underline">
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
              <span>* Chi phí được tính quy đổi tự động 1 USD = 25,400 VNĐ theo bảng giá Anthropic API chính thức.</span>
              <button
                onClick={() => setAuditModalOpen(false)}
                className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-medium text-white hover:bg-slate-900 transition"
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
