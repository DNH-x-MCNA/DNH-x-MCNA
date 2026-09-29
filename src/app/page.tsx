"use client";

import type { ChartSpec } from "./ReportChart";
import { useCallback, useEffect, useRef, useState } from "react";
import AdminUsersPanel from "./AdminUsersPanel";
import { AuditDashboard } from "./AuditDashboard";
import AuthScreens from "./AuthScreens";
import { ChangePasswordDialog } from "./ChangePasswordDialog";
import { MessageList } from "./ChatMessages";
import { ChatSidebar } from "./ChatSidebar";
import { Composer, ComposerHandle } from "./Composer";
import { EmptyState } from "./EmptyState";
import { IconArrowDown, IconCompose, IconMenu } from "./icons";
import {
  API_URL, AUTH_TOKEN_KEY, FreshnessItem, HistoryMessage, Message, SessionSummary, SubmitFeedback, UserInfo,
  authHeaders, getOrCreateSessionId, isAdminRole, rememberSessionId,
} from "./lib";
import { ConfirmDialog, IconButton, Skeleton, Spinner } from "./ui";

// Cach mep duoi (px) van coi la "dang o cuoi" - trong khoang nay cau tra loi dang stream tu keo xuong.
const STICK_TO_BOTTOM_PX = 120;

export default function Home() {
  const [sessionId, setSessionId] = useState<string>("default");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const composerRef = useRef<ComposerHandle>(null);

  // Cuon: chi tu keo xuong khi nguoi doc dang o cuoi, khong giat trang khi ho dang doc doan tren.
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  // Danh sach cuoc tro chuyen (kieu ChatGPT) - c_level thay cua tat ca nguoi, con lai chi thay cua
  // chinh minh (loc o backend, xem GET /sessions trong main.py).
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<SessionSummary | null>(null);

  // Trang thai dang nhap - kiem tra token da luu truoc khi cho vao giao dien chat
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  const [auditOpen, setAuditOpen] = useState(false);
  const [adminUsersOpen, setAdminUsersOpen] = useState(false);
  const [changePwdOpen, setChangePwdOpen] = useState(false);

  const isAdmin = isAdminRole(userInfo?.role);
  // Mat khau tam (tai khoan moi / vua duoc cap lai): bat buoc doi truoc khi dung, hop thoai khong dong duoc.
  const passwordChangeRequired = Boolean(userInfo?.must_change_password);

  function handleCancelQuestion() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }

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
      .catch(() => {})
      .finally(() => setSessionsLoaded(true));
  }

  function loadSessionHistory(sid: string) {
    setHistoryLoaded(false);
    stickToBottomRef.current = true;
    fetch(`${API_URL}/history/${sid}`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : []))
      .then((history: HistoryMessage[]) => {
        setMessages(
          history.map((h) => ({
            id: h.id,
            role: h.role === "user" ? "user" : "bot",
            text: h.content,
            charts: h.charts,
            queryId: h.query_id,
            feedbackRating: h.feedback_rating,
            feedbackCategory: h.feedback_category,
            feedbackComment: h.feedback_comment,
          })),
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
  }, [authToken, userInfo?.username]);

  function switchToSession(sid: string) {
    setSidebarOpen(false);
    if (sid === sessionId || loading) return;
    if (userInfo) rememberSessionId(userInfo.username, sid);
    setSessionId(sid);
    loadSessionHistory(sid);
  }

  async function confirmDeleteSession() {
    const sid = confirmDelete?.session_id;
    setConfirmDelete(null);
    if (!sid) return;
    try {
      await fetch(`${API_URL}/sessions/${sid}`, { method: "DELETE", headers: authHeaders(authToken) });
    } catch {
      // bo qua loi xoa
    }
    setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    if (sid === sessionId) startNewConversation();
  }

  async function handleLogout() {
    if (authToken) {
      try {
        await fetch(`${API_URL}/auth/logout`, { method: "POST", headers: authHeaders(authToken) });
      } catch {
        // bo qua loi logout phia server - van xoa token cuc bo
      }
    }
    clearLocalSession();
  }

  function clearLocalSession() {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    setAuthToken(null);
    setUserInfo(null);
    setChangePwdOpen(false);
    setMessages([]);
    setSessions([]);
    setSessionsLoaded(false);
  }

  const submitFeedback = useCallback<SubmitFeedback>(async (queryId, rating, category, comment) => {
    const response = await fetch(`${API_URL}/queries/${encodeURIComponent(queryId)}/feedback`, {
      method: "PUT",
      headers: authHeaders(authToken),
      body: JSON.stringify({ rating, category, comment }),
    });
    const payload = await response.json().catch(() => ({ detail: "Máy chủ trả về dữ liệu không hợp lệ" }));
    if (!response.ok) {
      throw new Error(payload.detail || `Không lưu được đánh giá (HTTP ${response.status})`);
    }
    setMessages((current) => current.map((message) => (
      message.role === "bot" && message.queryId === queryId
        ? { ...message, feedbackRating: payload.rating, feedbackCategory: payload.category, feedbackComment: payload.comment }
        : message
    )));
  }, [authToken]);

  // Tu keo xuong cuoi khi co noi dung moi - chi khi nguoi doc dang o cuoi (hoac vua gui cau hoi).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Man hinh chao (chua co tin nhan) doc tu tren xuong - ke ca khi vua roi mot cuoc dai da cuon.
    if (messages.length === 0) {
      el.scrollTop = 0;
      return;
    }
    if (stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, loading, historyLoaded]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distance < STICK_TO_BOTTOM_PX;
    setShowJumpToLatest(distance > STICK_TO_BOTTOM_PX * 2);
  }

  function jumpToLatest() {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottomRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }

  const canAsk =
    Boolean(userInfo) &&
    userInfo?.status !== "pending" &&
    userInfo?.role !== "admin_ops" &&
    !(userInfo?.quota_limit != null && userInfo.quota_remaining === 0);

  // 11/08/2026: dung /chat/stream (SSE) de giam cam giac "lag" - model suy luan xong moi tra loi nen
  // /chat (JSON 1 cuc) bat nguoi dung nhin man hinh trang. Voi stream, chu xuat hien dan ngay khi model
  // bat dau tra loi that. Doc thu cong ReadableStream (khong dung EventSource - API do CHI ho tro GET,
  // khong gui duoc body/POST can cho cau hoi + session_id + Authorization header).
  async function sendQuestion(question: string) {
    if (!question.trim() || loading || !canAsk) return;
    stickToBottomRef.current = true;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Bot message RONG dat truoc - cac text_delta se noi dan vao truong "text" cua CHINH dong nay
    // (xac dinh qua index, vi push xong la dong CUOI CUNG cua mang tai thoi diem nay).
    setMessages((prev) => [...prev, { role: "bot", text: "" }]);

    try {
      const res = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        headers: authHeaders(authToken),
        body: JSON.stringify({ question, session_id: sessionId }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: "Lỗi không xác định" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let doneReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE: moi event la 1 dong "data: {...}" ket thuc bang "\n\n". Buffer co the chua 0, 1 hoac
        // nhieu event chua hoan chinh trong 1 lan doc - tach het cac event DA DAY DU, giu lai phan con do.
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const jsonStr = line.slice(5).trim();
          if (!jsonStr) continue;
          let evt: {
            type: string; query_id?: string; text?: string; message?: string; answer?: string;
            sql_used?: string[]; columns?: string[] | null; rows?: unknown[][] | null;
            freshness?: FreshnessItem[]; charts?: ChartSpec[];
            quota_used?: number | null; quota_limit?: number | null;
            quota_remaining?: number | null; quota_resets_at?: string | null;
          };
          try {
            evt = JSON.parse(jsonStr);
          } catch {
            continue;
          }

          if (evt.type === "text_delta" && evt.text) {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "bot") next[next.length - 1] = { ...last, text: last.text + evt.text };
              return next;
            });
          } else if (evt.type === "done") {
            doneReceived = true;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "bot") {
                next[next.length - 1] = {
                  ...last,
                  queryId: evt.query_id,
                  text: evt.answer ?? last.text,
                  sqlUsed: evt.sql_used,
                  columns: evt.columns,
                  rows: evt.rows,
                  freshness: evt.freshness,
                  charts: evt.charts,
                };
              }
              return next;
            });
            // Cap nhat "con X/Y cau tuan nay" ngay sau moi cau tra loi - khong can goi rieng /auth/me.
            // quota_limit null (vai tro khong bi gioi han) -> giu nguyen, khong ghi de.
            if (evt.quota_limit != null) {
              setUserInfo((prev) => prev && {
                ...prev,
                quota_used: evt.quota_used,
                quota_limit: evt.quota_limit,
                quota_remaining: evt.quota_remaining,
                quota_resets_at: evt.quota_resets_at,
              });
            }
          } else if (evt.type === "error") {
            throw new Error(evt.message || "Lỗi không xác định");
          }
        }
      }

      if (!doneReceived) {
        // Stream ket thuc (backend dong ket noi) nhung chua thay event "done" - phong truong hop
        // tunnel dut giua chung sau khi da nhan mot vai text_delta.
        throw new Error("Kết nối bị ngắt trước khi nhận được câu trả lời đầy đủ.");
      }
      refreshSessions();
    } catch (e) {
      const aborted = (e as Error).name === "AbortError";
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        const replacement: Message = aborted
          ? { role: "bot", text: "", cancelled: true }
          : { role: "bot", text: (e as Error).message, error: true };
        // Bot message rong (chua nhan text_delta nao) -> thay bang thong bao, khong de lai bong rong.
        if (last && last.role === "bot" && !last.text) next[next.length - 1] = replacement;
        else next.push(replacement);
        return next;
      });
      if (aborted) refreshSessions();
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }

  // Giu ham on dinh cho MessageList (React.memo) - chi doi khi phien/quyen hoi doi.
  const sendRef = useRef(sendQuestion);
  useEffect(() => {
    sendRef.current = sendQuestion;
  });
  const retryQuestion = useCallback((q: string) => sendRef.current(q), []);

  function startNewConversation() {
    if (loading) return;
    // KHONG xoa cuoc cu - chi tao session moi va chuyen sang, cuoc cu van con trong sidebar.
    const newSid = crypto.randomUUID();
    if (userInfo) rememberSessionId(userInfo.username, newSid);
    setSessionId(newSid);
    setMessages([]);
    setHistoryLoaded(true);
    setSidebarOpen(false);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  }

  if (authChecking) {
    return (
      <div className="flex h-dvh items-center justify-center bg-soft">
        <Spinner className="h-5 w-5 text-slate-500" />
        <span className="sr-only">Đang kiểm tra đăng nhập…</span>
      </div>
    );
  }

  if (!authToken || !userInfo) {
    return (
      <AuthScreens
        onLoginSuccess={(token, user) => {
          if (typeof window !== "undefined") window.localStorage.setItem(AUTH_TOKEN_KEY, token);
          setAuthToken(token);
          setUserInfo({
            username: user.username,
            name: user.name,
            role: user.role,
            scope_value: user.scope_value,
            scope_channel: user.scope_channel,
            status: user.status,
            must_change_password: user.must_change_password,
            email: user.email,
            quota_used: user.quota_used,
            quota_limit: user.quota_limit,
            quota_remaining: user.quota_remaining,
            quota_resets_at: user.quota_resets_at,
          });
        }}
      />
    );
  }

  const currentTitle = sessions.find((s) => s.session_id === sessionId)?.title;
  const disabledReason =
    userInfo.status === "pending"
      ? "Tài khoản đang chờ duyệt — chưa thể hỏi dữ liệu"
      : userInfo.role === "admin_ops"
      ? "Tài khoản quản trị không dùng để hỏi dữ liệu kinh doanh"
      : userInfo.quota_limit != null && userInfo.quota_remaining === 0
      ? `Đã dùng hết ${userInfo.quota_limit} câu hỏi của tuần này${userInfo.quota_resets_at ? ` · làm mới ${new Date(userInfo.quota_resets_at).toLocaleString("vi-VN", { weekday: "long", hour: "2-digit", minute: "2-digit" })}` : ""}`
      : null;
  const showEmpty = historyLoaded && messages.length === 0;

  return (
    <div className="flex h-dvh overflow-hidden bg-white">
      <ChatSidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        user={userInfo}
        isAdmin={isAdmin}
        sessions={sessions}
        sessionsLoaded={sessionsLoaded}
        currentSessionId={sessionId}
        busy={loading}
        onSelect={switchToSession}
        onNew={startNewConversation}
        onRequestDelete={setConfirmDelete}
        onOpenAudit={() => { setSidebarOpen(false); setAuditOpen(true); }}
        onOpenUsers={() => { setSidebarOpen(false); setAdminUsersOpen(true); }}
        onChangePassword={() => { setSidebarOpen(false); setChangePwdOpen(true); }}
        onLogout={handleLogout}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 sm:px-5">
          <IconButton label="Mở lịch sử trò chuyện" onClick={() => setSidebarOpen(true)} className="md:hidden">
            <IconMenu className="h-5 w-5" />
          </IconButton>
          <h2 className="min-w-0 flex-1 truncate text-[15px] font-semibold text-navy">
            {messages.length > 0 ? currentTitle || "Cuộc trò chuyện mới" : "Cuộc trò chuyện mới"}
          </h2>
          <IconButton label="Cuộc trò chuyện mới" onClick={startNewConversation} disabled={loading} className="md:hidden">
            <IconCompose className="h-5 w-5" />
          </IconButton>
        </header>

        <main className="relative flex min-h-0 flex-1 flex-col">
          <div ref={scrollRef} onScroll={handleScroll} className="custom-scroll min-h-0 flex-1 overflow-y-auto">
            {!historyLoaded ? (
              <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-10 sm:px-6">
                <Skeleton className="ml-auto h-10 w-2/5 rounded-2xl" />
                <div className="space-y-2.5">
                  <Skeleton className="h-4 w-11/12" />
                  <Skeleton className="h-4 w-4/5" />
                  <Skeleton className="h-4 w-3/5" />
                </div>
              </div>
            ) : showEmpty ? (
              <EmptyState
                user={userInfo}
                isAdmin={isAdmin}
                onAsk={sendQuestion}
                onChangePassword={() => setChangePwdOpen(true)}
                onOpenAudit={() => setAuditOpen(true)}
                onOpenUsers={() => setAdminUsersOpen(true)}
              />
            ) : (
              <div className="mx-auto w-full max-w-3xl px-4 pb-10 pt-8 sm:px-6">
                <MessageList messages={messages} loading={loading} onRetry={retryQuestion} onFeedback={submitFeedback} />
              </div>
            )}
          </div>

          {showJumpToLatest && !showEmpty && (
            <button
              type="button"
              onClick={jumpToLatest}
              aria-label="Xuống tin nhắn mới nhất"
              title="Xuống tin nhắn mới nhất"
              className="absolute bottom-32 left-1/2 flex h-9 w-9 -translate-x-1/2 animate-fade-in items-center justify-center rounded-full bg-white text-slate-600 shadow-raised ring-1 ring-line transition hover:text-navy sm:bottom-36"
            >
              <IconArrowDown className="h-[18px] w-[18px]" />
            </button>
          )}

          <Composer
            ref={composerRef}
            value={input}
            onChange={setInput}
            onSubmit={() => sendQuestion(input)}
            onStop={handleCancelQuestion}
            loading={loading}
            disabledReason={disabledReason}
            quota={userInfo}
          />
        </main>
      </div>

      {auditOpen && <AuditDashboard authToken={authToken} onClose={() => setAuditOpen(false)} />}
      {adminUsersOpen && (
        <AdminUsersPanel authToken={authToken} currentRole={userInfo.role} onClose={() => setAdminUsersOpen(false)} />
      )}
      <ChangePasswordDialog
        open={changePwdOpen || passwordChangeRequired}
        forced={passwordChangeRequired}
        authToken={authToken}
        onClose={() => setChangePwdOpen(false)}
        onPasswordChanged={clearLocalSession}
      />
      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Xóa cuộc trò chuyện?"
        message={<>“{confirmDelete?.title || "Cuộc trò chuyện mới"}” sẽ bị xóa vĩnh viễn và không thể khôi phục.</>}
        confirmLabel="Xóa"
        onConfirm={confirmDeleteSession}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
