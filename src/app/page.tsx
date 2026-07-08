"use client";

import { useState, useRef, useEffect, FormEvent, ReactNode } from "react";
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

type Message = {
  role: "user" | "bot";
  text: string;
  sqlUsed?: string[];
  columns?: string[] | null;
  rows?: unknown[][] | null;
  error?: boolean;
};

const SAMPLE_QUESTIONS = [
  "Doanh thu hôm nay bao nhiêu?",
  "Top 10 sản phẩm bán chạy nhất?",
  "So sánh doanh thu tháng này với tháng trước?",
  "Nhân viên nào chưa đạt KPI?",
  "Công nợ quá hạn nhiều nhất là khách hàng nào?",
];

// Goi vao route noi bo (/api/...) cua chinh Next.js thay vi goi thang backend - route nay chay
// server-side tren Vercel, giu BACKEND_API_URL/BACKEND_API_KEY (khong phai NEXT_PUBLIC_) nen trinh
// duyet khong bao gio thay duoc URL that/API key cua backend.
const API_URL = "/api";
const SESSION_KEY = "dnh_chat_session_id";
const API_HEADERS: HeadersInit = { "Content-Type": "application/json" };

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

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "default";
  let sid = window.localStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    window.localStorage.setItem(SESSION_KEY, sid);
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

  // Khoi tao session + nap lai lich su hoi thoai cu (neu co) khi mo trang
  useEffect(() => {
    const sid = getOrCreateSessionId();
    setSessionId(sid);
    fetch(`${API_URL}/history/${sid}`, { headers: API_HEADERS })
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
  }, []);

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
        headers: API_HEADERS,
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
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: `Xin lỗi, có lỗi xảy ra: ${(e as Error).message}`, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function startNewConversation() {
    if (loading) return;
    try {
      await fetch(`${API_URL}/clear/${sessionId}`, { method: "POST", headers: API_HEADERS });
    } catch {
      // bo qua loi xoa - van tao session moi phia client
    }
    const newSid = crypto.randomUUID();
    window.localStorage.setItem(SESSION_KEY, newSid);
    setSessionId(newSid);
    setMessages([]);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendQuestion(input);
  }

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-slate-900 px-6 py-4 text-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/namha-logo.png" alt="NAMHA PHARMA" className="h-9 w-auto" />
            <div>
              <div className="text-xs tracking-wide text-blue-300">DƯỢC NAM HÀ · AI ANALYST</div>
              <h1 className="text-xl font-bold">Trợ lý phân tích dữ liệu kinh doanh</h1>
            </div>
          </div>
          <button
            onClick={startNewConversation}
            title="Bắt đầu cuộc trò chuyện mới (xóa ngữ cảnh hiện tại)"
            className="rounded-full border border-slate-600 px-4 py-2 text-xs text-slate-200 transition hover:border-blue-400 hover:text-blue-300"
          >
            + Cuộc trò chuyện mới
          </button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-hidden px-4">
        <div className="flex-1 overflow-y-auto py-6">
          {historyLoaded && messages.length === 0 && (
            <div className="mt-8">
              <p className="mb-3 text-sm text-slate-500">Thử hỏi một trong các câu sau:</p>
              <div className="flex flex-wrap gap-2">
                {SAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendQuestion(q)}
                    className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 transition hover:border-blue-400 hover:text-blue-600"
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
          </div>
          <div ref={bottomRef} />
        </div>

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
  );
}
