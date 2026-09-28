// Kieu du lieu, hang so API va ham dinh dang dung chung (tach tu page.tsx 28/09/2026 khi thiet ke lai
// giao dien - logic giu nguyen).
import { ROLE_LABELS } from "./roleLabels";

// Ty gia USD -> VND cho cac so chi phi AI hien thi o frontend. Phai khop voi
// backend/pricing.py::USD_TO_VND_RATE - backend tra san *_vnd cho phan lon so lieu, rieng phan
// "chua quy duoc cho ai" dang quy doi tai day nen van can hang so nay.
export const USD_TO_VND_RATE = 26334.5;

// Goi vao route noi bo (/api/...) cua chinh Next.js thay vi goi thang backend - route nay chay
// server-side tren Vercel, giu BACKEND_API_URL/BACKEND_API_KEY (khong phai NEXT_PUBLIC_) nen trinh
// duyet khong bao gio thay duoc URL that/API key cua backend.
export const API_URL = "/api";
export const SESSION_KEY = "dnh_chat_session_id";
export const AUTH_TOKEN_KEY = "dnh_auth_token";

export function authHeaders(token: string | null): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export type FeedbackRating = 1 | -1;

export type HistoryMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  query_id?: string | null;
  feedback_rating?: FeedbackRating | null;
  feedback_category?: string | null;
  feedback_comment?: string | null;
};

// Backend tra moc du lieu rieng o truong `freshness` va CAM model tu viet dong "du lieu den ngay..."
// (xem THOI DIEM DU LIEU trong system prompt). Truoc 13/09/2026 giao dien khong doc truong nay nen
// cau tra loi mat han moc du lieu - nguoi cham UAT khong biet so lech la do kho dong bo sau Bravo
// hay do tinh sai (V24).
export type FreshnessItem = {
  source_name?: string;
  business_data_date?: string | null;
  sync_completed_at?: string | null;
  snapshot_date?: string | null;
  is_stale?: boolean;
  warning?: string | null;
};

export type SubmitFeedback = (
  queryId: string,
  rating: FeedbackRating,
  category?: string,
  comment?: string,
) => Promise<void>;

export const FEEDBACK_CATEGORY_OPTIONS = [
  ["wrong_number", "Số liệu không đúng"],
  ["missing_data", "Thiếu dữ liệu"],
  ["wrong_scope", "Sai phạm vi/kỳ báo cáo"],
  ["not_understood", "Chưa hiểu đúng câu hỏi"],
  ["too_slow", "Phản hồi quá chậm"],
  ["unclear_answer", "Câu trả lời khó hiểu"],
  ["other", "Lý do khác"],
] as const;

export const FEEDBACK_CATEGORY_LABELS = Object.fromEntries(FEEDBACK_CATEGORY_OPTIONS) as Record<string, string>;

export type SessionSummary = {
  session_id: string;
  title: string | null;
  owner_username: string;
  owner_name: string | null;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id?: number;
  role: "user" | "bot";
  text: string;
  queryId?: string | null;
  freshness?: FreshnessItem[];
  sqlUsed?: string[];
  columns?: string[] | null;
  rows?: unknown[][] | null;
  error?: boolean;
  cancelled?: boolean;
  feedbackRating?: FeedbackRating | null;
  feedbackCategory?: string | null;
  feedbackComment?: string | null;
};

export type UserInfo = {
  username: string;
  name: string | null;
  role: string;
  scope_value: string | null;
  scope_channel?: string | null;
  status?: string;
  must_change_password?: boolean;
  email?: string | null;
  quota_used?: number | null;
  quota_limit?: number | null;
  quota_remaining?: number | null;
  quota_resets_at?: string | null;
};

// 28/07/2026: CHI dua vao role, KHONG suy quyen tu chuoi username (lo hong R-I da va o backend: suy
// quyen tu TEN tai khoan nghia la tai khoan ten "c_level.tro.ly" tu nhien thay chi phi toan cong ty).
// O frontend chi an/hien nut, quyen that da chan o backend qua scope_role.
export function isAdminRole(role: string | undefined | null): boolean {
  const r = (role || "").toLowerCase();
  return r === "c_level" || r === "admin" || r === "admin_ops";
}

const REGION_LABELS: Record<string, string> = { MB: "Miền Bắc", MT: "Miền Trung", MN: "Miền Nam" };

/** Pham vi du lieu nguoi dung duoc xem - hien o man hinh chao va menu tai khoan de nguoi hoi biet
 *  so lieu tra ve thuoc pham vi nao. Quyen that van do backend chan. */
export function scopeLabel(user: Pick<UserInfo, "role" | "scope_value" | "scope_channel">): string {
  const parts: string[] = [];
  if (user.scope_value) parts.push(REGION_LABELS[user.scope_value] || user.scope_value);
  if (user.scope_channel) parts.push(`Kênh ${user.scope_channel}`);
  if (parts.length) return parts.join(" · ");
  return isAdminRole(user.role) ? "Toàn công ty" : "Theo phân quyền của tài khoản";
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] || role;
}

export function displayName(user: Pick<UserInfo, "name" | "username">): string {
  return user.name || user.username;
}

/** Bo dau tieng Viet de tim kiem "cong no" khop "Cong no". */
export function foldVietnamese(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
}

/** "2026-09-28T19:59:03" / "2026-09-28 19:59" -> "28/09/2026 19:59" (giu nguyen neu khong dung dang). */
export function formatDateTime(value?: string | null, withSeconds = false): string {
  if (!value) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(value);
  if (!m) return value;
  const date = `${m[3]}/${m[2]}/${m[1]}`;
  if (!m[4]) return date;
  return `${date} ${m[4]}:${m[5]}${withSeconds && m[6] ? `:${m[6]}` : ""}`;
}

export function formatVnd(value: number): string {
  return `${Math.round(value).toLocaleString("vi-VN")} đ`;
}

export function compactTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2).replace(".", ",")}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(value);
}

export function formatRelativeTime(iso: string): string {
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
export type SessionGroup = { label: string; items: SessionSummary[] };
export function groupSessionsByDate(list: SessionSummary[]): SessionGroup[] {
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

function sessionKeyFor(username: string): string {
  // Rieng key theo tung username - tranh truong hop 2 tai khoan khac nhau dung chung 1 trinh duyet
  // (vd dang xuat roi dang nhap tai khoan khac) vo tinh dung chung 1 session_id cu, dan den bi 403
  // "khong co quyen xem cuoc tro chuyen nay" vi session_id do la cua nguoi dung TRUOC.
  return `${SESSION_KEY}_${username}`;
}

export function getOrCreateSessionId(username: string): string {
  if (typeof window === "undefined") return "default";
  const key = sessionKeyFor(username);
  let sid = window.localStorage.getItem(key);
  if (!sid) {
    sid = crypto.randomUUID();
    window.localStorage.setItem(key, sid);
  }
  return sid;
}

export function rememberSessionId(username: string, sid: string): void {
  window.localStorage.setItem(sessionKeyFor(username), sid);
}
