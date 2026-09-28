"use client";

// Dashboard Audit Log & chi phi AI cho C-Level. Tach tu page.tsx 28/09/2026 khi thiet ke lai giao dien;
// logic loc/goi API giu nguyen.
import { ReactNode, useEffect, useState } from "react";
import {
  IconChart, IconChevronLeft, IconChevronRight, IconClose, IconRefresh, IconThumbDown, IconThumbUp, IconWarning,
} from "./icons";
import {
  API_URL, FEEDBACK_CATEGORY_LABELS, FeedbackRating, USD_TO_VND_RATE, authHeaders, compactTokens, formatDateTime,
  formatVnd,
} from "./lib";
import { ROLE_LABELS } from "./roleLabels";
import { ExportableTable } from "./TableExport";
import {
  Badge, Button, CompactInput, Dialog, DialogBody, DialogFooter, DialogHeader, IconButton, Notice,
  SegmentedControl, Select, Skeleton, cx,
} from "./ui";

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
  date: string | null;
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
  providers: ProviderCostItem[];
};

// 17/08/2026: mot ngay co the dung NHIEU nha cung cap / nhieu key (dang chay thu DeepSeek song song
// Claude). Gop chung mot cot thi khong biet tien cua ben nao, cung khong so duoc ben nao re hon.
type ProviderCostItem = {
  provider: string;
  api_key_id: string;
  model: string;
  query_count: number;
  cost_usd: number;
  cost_vnd: number;
  total_tokens?: number;
};

// Mau dinh danh nha cung cap - GAN CO DINH theo ten, khong xoay vong theo thu tu xuat hien: loc bot mot
// nguon ma cac nguon con lai doi mau thi nguoi doc tuong du lieu doi. Cap ho phach/tim da kiem: tach bach
// ca voi mat mu mau (protan). Ho phach tuong phan thap so voi nen nen KHONG dung mot minh: luon kem so
// ghi tren dau cot va bang chi tiet ben duoi.
const MAU_NHA_CUNG_CAP: Record<string, string> = {
  Anthropic: "#f59e0b",
  DeepSeek: "#8b5cf6",
};
const MAU_KHAC = "#94a3b8"; // nguon la / ban ghi cu chua ghi nhan - xam trung tinh, khong tranh mau

function mauNhaCungCap(ten: string): string {
  return MAU_NHA_CUNG_CAP[ten] || MAU_KHAC;
}

// 24/09/2026: truoc day moi trang thai la deu hien "Loi". Het han muc API, luot bi bo do, nguoi dung
// dung giua chung, kiem tra tu dong... phai phan biet duoc voi chatbot hong.
const QUERY_STATUS_LABELS: Record<string, { label: string; tone: "success" | "warning" | "brand" | "neutral" }> = {
  completed: { label: "Hoàn thành", tone: "success" },
  success: { label: "Hoàn thành", tone: "success" },
  ok: { label: "Hoàn thành", tone: "success" },
  partial_timeout: { label: "Trả lời một phần", tone: "warning" },
  running: { label: "Đang chạy", tone: "brand" },
  api_credit_exhausted: { label: "Hết hạn mức API", tone: "warning" },
  abandoned: { label: "Bị bỏ dở", tone: "neutral" },
  cancelled: { label: "Người dùng dừng", tone: "neutral" },
  tool_check: { label: "Kiểm tra tự động", tone: "neutral" },
};

function queryStatusLabel(status: string | null | undefined): { label: string; tone: "success" | "warning" | "brand" | "neutral" | "danger" } {
  return QUERY_STATUS_LABELS[status || ""] || { label: "Lỗi", tone: "danger" };
}

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
  provider_breakdown: ProviderCostItem[];
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
  tool_duration_ms?: number | null;
  log_source?: "audit" | "query_run" | "security" | "cost_log";
  session_id: string | null;
  query_id?: string | null;
  row_count?: number | null;
  error_message?: string | null;
  feedback_rating?: FeedbackRating | null;
  feedback_category?: string | null;
  feedback_comment?: string | null;
  feedback_by?: string | null;
  feedback_at?: string | null;
  session_input_tokens: number;
  session_output_tokens: number;
  session_total_tokens: number;
  session_cost_usd: number;
  session_cost_vnd: number;
  api_provider?: string | null;
  api_model?: string | null;
};

type AuditDashboardData = {
  summary: AuditSummary;
  user_breakdown: UserBreakdownItem[];
  logs: QueryLogItem[];
};

type Tab = "users" | "weekly" | "logs";

const TH = "sticky top-0 z-10 whitespace-nowrap border-b border-line bg-soft px-3.5 py-2.5 text-[12.5px] font-medium text-slate-500";
const TD = "border-b border-slate-100 px-3.5 py-2.5 text-slate-700";

/** Chi mount khi dang mo (page.tsx): mo la tai ngay du lieu ky + du lieu tuan, dong la bo trang thai. */
export function AuditDashboard({ authToken, onClose }: { authToken: string | null; onClose: () => void }) {
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditData, setAuditData] = useState<AuditDashboardData | null>(null);
  const [auditDays, setAuditDays] = useState<number>(30);
  // Rong = dang loc theo "N ngay gan nhat" (auditDays); co gia tri (YYYY-MM-DD) = loc dung 1 ngay.
  const [auditSpecificDate, setAuditSpecificDate] = useState<string>("");
  const [auditUserFilter, setAuditUserFilter] = useState<string>("all");
  const [auditRoleFilter, setAuditRoleFilter] = useState<string>("all");
  const [tab, setTab] = useState<Tab>("users");
  const [weeklyData, setWeeklyData] = useState<WeeklyAuditData | null>(null);
  const [weeklyOffset, setWeeklyOffset] = useState<number>(0);
  const [weeklyLoading, setWeeklyLoading] = useState<boolean>(true);

  // request*: chi goi API va nhan ket qua; co "dang tai" do noi goi bat truoc (luc mount thi san la true).
  function requestAudit(daysVal: number, userVal: string, dateVal: string, roleVal: string) {
    if (!authToken) return;
    const params = new URLSearchParams({ limit: "300" });
    if (dateVal) params.append("date", dateVal);
    else params.append("days", String(daysVal));
    if (userVal && userVal !== "all") params.append("user_filter", userVal);
    if (roleVal && roleVal !== "all") params.append("role_filter", roleVal);
    fetch(`${API_URL}/audit-logs?${params.toString()}`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: AuditDashboardData | null) => {
        if (data) setAuditData(data);
      })
      .catch((e) => console.error("Error fetching audit logs:", e))
      .finally(() => setAuditLoading(false));
  }

  function requestWeekly(offset: number) {
    if (!authToken) return;
    fetch(`${API_URL}/audit-logs/weekly?week_offset=${offset}`, { headers: authHeaders(authToken) })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: WeeklyAuditData | null) => {
        if (data) setWeeklyData(data);
      })
      .catch((e) => console.error("Error fetching weekly audit logs:", e))
      .finally(() => setWeeklyLoading(false));
  }

  const fetchAuditData = (daysVal: number, userVal: string, dateVal: string = "", roleVal: string = "all") => {
    setAuditLoading(true);
    requestAudit(daysVal, userVal, dateVal, roleVal);
  };

  // Vao tab tuan / doi tuan thi tai lai du lieu tuan (giong ban cu).
  function changeWeek(offset: number) {
    setWeeklyOffset(offset);
    setWeeklyLoading(true);
    requestWeekly(offset);
  }

  function changeTab(next: Tab) {
    setTab(next);
    if (next === "weekly") changeWeek(weeklyOffset);
  }

  useEffect(() => {
    requestAudit(30, "all", "", "all");
    requestWeekly(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const effectiveRate =
    auditData && auditData.summary.total_cost_usd > 0
      ? auditData.summary.total_cost_vnd / auditData.summary.total_cost_usd
      : USD_TO_VND_RATE;

  return (
    <Dialog open onClose={onClose} labelledBy="audit-title" size="full" className="sm:h-[88vh]">
      <DialogHeader
        id="audit-title"
        icon={<IconChart className="h-[18px] w-[18px]" />}
        title="Chi phí AI & nhật ký truy vấn"
        description="Dành cho Ban điều hành · số liệu lấy trực tiếp từ sổ chi phí"
        onClose={onClose}
      />

      <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3 sm:px-6">
        <SegmentedControl<Tab>
          label="Chế độ xem"
          value={tab}
          onChange={changeTab}
          options={[
            { value: "users", label: "Theo người dùng" },
            { value: "weekly", label: "Theo tuần" },
            { value: "logs", label: "Nhật ký truy vấn" },
          ]}
        />
        {tab !== "weekly" && (
          <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
            <Select
              compact
              value={auditDays}
              disabled={Boolean(auditSpecificDate)}
              aria-label="Khoảng thời gian"
              onChange={(e) => {
                const val = Number(e.target.value);
                setAuditDays(val);
                fetchAuditData(val, auditUserFilter, "", auditRoleFilter);
              }}
            >
              <option value={7}>7 ngày gần nhất</option>
              <option value={30}>30 ngày gần nhất</option>
              <option value={90}>90 ngày gần nhất</option>
            </Select>
            <div className="relative flex items-center">
              <CompactInput
                type="date"
                aria-label="Chọn một ngày cụ thể"
                title="Xem đúng một ngày"
                value={auditSpecificDate}
                className={cx("w-[138px]", auditSpecificDate && "pr-8")}
                onChange={(e) => {
                  const val = e.target.value;
                  setAuditSpecificDate(val);
                  fetchAuditData(auditDays, auditUserFilter, val, auditRoleFilter);
                }}
              />
              {auditSpecificDate && (
                <IconButton
                  label="Bỏ lọc theo ngày"
                  size="sm"
                  className="absolute right-1"
                  onClick={() => {
                    setAuditSpecificDate("");
                    fetchAuditData(auditDays, auditUserFilter, "", auditRoleFilter);
                  }}
                >
                  <IconClose className="h-3.5 w-3.5" />
                </IconButton>
              )}
            </div>
            <Select
              compact
              className="max-w-[160px]"
              value={auditUserFilter}
              aria-label="Người dùng"
              onChange={(e) => {
                const val = e.target.value;
                setAuditUserFilter(val);
                fetchAuditData(auditDays, val, auditSpecificDate, auditRoleFilter);
              }}
            >
              <option value="all">Tất cả người dùng</option>
              {auditData?.user_breakdown.map((u) => (
                <option key={u.username} value={u.username}>{u.user_name} ({u.username})</option>
              ))}
            </Select>
            <Select
              compact
              className="max-w-[160px]"
              value={auditRoleFilter}
              aria-label="Chức vụ"
              onChange={(e) => {
                const val = e.target.value;
                setAuditRoleFilter(val);
                fetchAuditData(auditDays, auditUserFilter, auditSpecificDate, val);
              }}
            >
              <option value="all">Tất cả chức vụ</option>
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </Select>
            <IconButton
              label={auditLoading ? "Đang tải…" : "Làm mới"}
              disabled={auditLoading}
              onClick={() => fetchAuditData(auditDays, auditUserFilter, auditSpecificDate, auditRoleFilter)}
            >
              <IconRefresh className={cx("h-[18px] w-[18px]", auditLoading && "animate-spin")} />
            </IconButton>
          </div>
        )}
      </div>

      <DialogBody className="bg-soft/60">
        {tab === "weekly" ? (
          <WeeklyView data={weeklyData} loading={weeklyLoading} offset={weeklyOffset} onChangeWeek={changeWeek} />
        ) : auditLoading && !auditData ? (
          <div className="grid gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
          </div>
        ) : !auditData ? (
          <div className="flex h-64 items-center justify-center text-[14px] text-slate-400">Không tải được dữ liệu Audit Log.</div>
        ) : (
          <div className="space-y-5">
            <SummaryCards summary={auditData.summary} effectiveRate={effectiveRate} />
            {tab === "users" ? <UsersTable rows={auditData.user_breakdown} /> : <LogsTable logs={auditData.logs} />}
          </div>
        )}
      </DialogBody>

      <DialogFooter className="justify-between">
        <p className="max-w-4xl text-[12px] leading-relaxed text-slate-500">
          Chi phí quy đổi theo tỷ giá {Math.round(effectiveRate).toLocaleString("vi-VN")} đ/USD. Nhà cung cấp và model lấy từ
          log API thực tế của từng lượt; tổng lấy thẳng từ sổ chi phí nên luôn đúng, kể cả phần chưa quy được về người dùng
          cụ thể. <span className="font-medium text-slate-700">Số liệu ở đây chia ngày theo giờ Việt Nam, còn Anthropic Console
          chia theo giờ UTC (lệch 7 tiếng)</span> — không so trực tiếp từng ngày giữa hai nơi được; muốn đối chiếu hãy so tổng
          nhiều ngày liền nhau.
        </p>
        <Button variant="secondary" onClick={onClose}>Đóng</Button>
      </DialogFooter>
    </Dialog>
  );
}

function StatCard({ label, value, children }: { label: string; value: ReactNode; children?: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-inset ring-line">
      <div className="text-[13px] text-slate-500">{label}</div>
      <div className="mt-1.5 text-[24px] font-semibold leading-tight tracking-tight text-navy tabular-nums">{value}</div>
      {children && <div className="mt-2 text-[12.5px] leading-relaxed text-slate-500">{children}</div>}
    </div>
  );
}

function SummaryCards({ summary, effectiveRate }: { summary: AuditSummary; effectiveRate: number }) {
  // Ty gia HIEN THI phai la ty gia BACKEND DA THUC SU DUNG de quy doi, suy nguoc tu chinh du lieu tra
  // ve - khong duoc lay hang so cua frontend. Hai ben co the lech nhau khi frontend da deploy con
  // backend tren may 24 thi chua; khi do ghi hang so frontend len the la noi sai ve so tien ngay ben tren.
  const isStale = Math.abs(effectiveRate - USD_TO_VND_RATE) > 1;
  const tIn = summary.total_input_tokens;
  const tOut = summary.total_output_tokens;
  const tCache = summary.total_cache_tokens;
  const total = tIn + tOut + tCache;
  const pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="Tổng chi phí AI" value={formatVnd(summary.total_cost_vnd)}>
        <div className="tabular-nums">≈ ${summary.total_cost_usd.toFixed(4)} USD</div>
        <div className="mt-1 inline-flex items-center gap-1" title={isStale ? `Máy chủ đang dùng tỷ giá cũ. Bản mới nhất: ${USD_TO_VND_RATE.toLocaleString("vi-VN")} đ` : undefined}>
          1 USD = {Math.round(effectiveRate).toLocaleString("vi-VN")} đ
          {isStale && <IconWarning className="h-3.5 w-3.5 text-amber-600" />}
        </div>
        {summary.unattributed_cost_usd > 0 && (
          <div className="mt-1">
            Trong đó {formatVnd(summary.unattributed_cost_usd * effectiveRate)} chưa quy được cho người dùng cụ thể.
          </div>
        )}
      </StatCard>
      <StatCard label="Token đã dùng" value={summary.grand_total_tokens.toLocaleString("vi-VN")}>
        <div className="flex h-1.5 overflow-hidden rounded-full bg-sunken">
          <div style={{ width: `${pct(tIn)}%` }} className="bg-brand" title={`Input: ${tIn.toLocaleString("vi-VN")}`} />
          <div style={{ width: `${pct(tOut)}%` }} className="bg-brand-blue" title={`Output: ${tOut.toLocaleString("vi-VN")}`} />
          {tCache > 0 && <div style={{ width: `${pct(tCache)}%` }} className="bg-sky-300" title={`Cache: ${tCache.toLocaleString("vi-VN")}`} />}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          <Legend className="bg-brand" label={`Input ${compactTokens(tIn)}`} />
          <Legend className="bg-brand-blue" label={`Output ${compactTokens(tOut)}`} />
          {tCache > 0 && <Legend className="bg-sky-300" label={`Cache ${compactTokens(tCache)}`} />}
        </div>
      </StatCard>
      <StatCard label="Lượt hỏi" value={summary.total_queries.toLocaleString("vi-VN")}>
        {summary.date
          ? `Ngày ${summary.date.split("-").reverse().join("/")}`
          : `Trong ${summary.days} ngày · trung bình ${(summary.total_queries / Math.max(1, summary.days)).toFixed(1).replace(".", ",")} lượt/ngày`}
      </StatCard>
      <StatCard label="Người dùng hoạt động" value={summary.unique_users_count.toLocaleString("vi-VN")}>
        Có ít nhất một lượt hỏi trong kỳ.
      </StatCard>
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums">
      <span className={cx("h-2 w-2 rounded-full", className)} />
      {label}
    </span>
  );
}

function TableCard({ children, className, nhan }: { children: ReactNode; className?: string; nhan: string }) {
  return (
    <ExportableTable nhan={nhan} className={cx("custom-scroll max-h-[460px] overflow-auto rounded-2xl bg-white shadow-card ring-1 ring-inset ring-line", className)}>
      {children}
    </ExportableTable>
  );
}

function UsersTable({ rows }: { rows: UserBreakdownItem[] }) {
  // "Cao nhat" chi xet NGUOI DUNG THAT - dong "(chua quy duoc)" khong phai mot nguoi, truoc day no
  // thuong lon nhat bang nen bi danh dau nham.
  const realUsers = rows.filter((u) => !u.is_unattributed);
  const maxCost = Math.max(0, ...realUsers.map((u) => u.cost_usd));
  const hasUnattributed = rows.some((u) => u.is_unattributed);
  const hasZeroCostUser = realUsers.some((u) => u.query_count > 0 && u.cost_usd === 0);
  return (
    <div className="space-y-3">
      {(hasUnattributed || hasZeroCostUser) && (
        <Notice tone="info" title="Vì sao có dòng 0 đồng và dòng “chưa quy được”">
          Sổ chi phí chỉ bắt đầu ghi kèm tên tài khoản từ 29/07/2026. Những lượt hỏi trước mốc đó vẫn được đếm ở
          cột “Số câu hỏi” nhưng không nối ngược được sang tiền, nên phần tiền của chúng dồn vào dòng cuối bảng.
          Tổng tiền toàn công ty vẫn đúng.
        </Notice>
      )}
      <TableCard nhan="chi-phi-ai-theo-nguoi-dung">
        <table className="w-full border-collapse text-[13.5px] tabular-nums">
          <thead>
            <tr>
              <th className={cx(TH, "text-left")}>Người dùng</th>
              <th className={cx(TH, "text-left")}>Tài khoản</th>
              <th className={cx(TH, "text-right")}>Số câu hỏi</th>
              <th className={cx(TH, "text-right")}>Input</th>
              <th className={cx(TH, "text-right")}>Output</th>
              <th className={cx(TH, "text-right")}>Cache</th>
              <th className={cx(TH, "text-right")}>Tổng token</th>
              <th className={cx(TH, "text-right")}>Chi phí (USD)</th>
              <th className={cx(TH, "text-right")}>Chi phí (VNĐ)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => {
              const isTop = !u.is_unattributed && maxCost > 0 && u.cost_usd === maxCost;
              // Ban backend cu chua tra cache_tokens - suy nguoc tu tong de cot Cache van dung thay vi hien 0.
              const cacheTokens = u.cache_tokens ?? Math.max(0, u.total_tokens - u.input_tokens - u.output_tokens);
              return (
                <tr key={u.username} className={cx("transition-colors hover:bg-slate-50/70", u.is_unattributed && "italic text-slate-500")}>
                  <td className={cx(TD, "font-medium text-navy")}>
                    <span className="inline-flex items-center gap-2">
                      {u.user_name}
                      {isTop && <Badge tone="warning" className="not-italic">Cao nhất</Badge>}
                    </span>
                  </td>
                  <td className={cx(TD, "font-mono text-[12.5px] text-slate-500")}>{u.username}</td>
                  <td className={cx(TD, "text-right")}>{u.query_count}</td>
                  <td className={cx(TD, "text-right")}>{u.input_tokens.toLocaleString("vi-VN")}</td>
                  <td className={cx(TD, "text-right")}>{u.output_tokens.toLocaleString("vi-VN")}</td>
                  <td className={cx(TD, "text-right")}>{cacheTokens.toLocaleString("vi-VN")}</td>
                  <td className={cx(TD, "text-right text-slate-800")}>{u.total_tokens.toLocaleString("vi-VN")}</td>
                  <td className={cx(TD, "text-right")}>${u.cost_usd.toFixed(4)}</td>
                  <td className={cx(TD, "text-right font-semibold text-navy")}>{formatVnd(u.cost_vnd)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableCard>
    </div>
  );
}

function LogsTable({ logs }: { logs: QueryLogItem[] }) {
  // Bang nay chi de hien cau hoi thuc su gui cho AI - loai su kien dang nhap/doi MK/tao tai khoan (sql
  // bat dau "<auth:"/"<admin:"), vi cac su kien do da co rieng tab "Nhat ky bao mat" trong Tai khoan
  // nhan vien; tron chung vao day gay kho doc (06/08/2026).
  const queryOnlyLogs = logs.filter((l) => {
    const s = l.sql || "";
    return !s.startsWith("<auth:") && !s.startsWith("<admin:");
  });
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-slate-500">
        {queryOnlyLogs.length} lượt hỏi gần nhất. Cột token và chi phí tính cho <span className="font-medium text-slate-700">cả phiên</span> chứa lượt hỏi đó.
      </p>
      <TableCard nhan="nhat-ky-truy-van">
        <table className="w-full border-collapse text-[13.5px] tabular-nums">
          <thead>
            <tr>
              <th className={cx(TH, "text-left")}>Thời gian</th>
              <th className={cx(TH, "text-left")}>Người dùng</th>
              <th className={cx(TH, "text-left")}>API sử dụng</th>
              <th className={cx(TH, "text-left")}>Câu hỏi</th>
              <th className={cx(TH, "text-left")}>Trạng thái</th>
              <th className={cx(TH, "text-left")}>Đánh giá</th>
              <th className={cx(TH, "text-left")}>Nhận xét</th>
              <th className={cx(TH, "text-right")}>Input</th>
              <th className={cx(TH, "text-right")}>Output</th>
              <th className={cx(TH, "text-right")}>Chi phí</th>
              <th className={cx(TH, "text-right")}>Thời gian chạy</th>
              <th className={cx(TH, "text-left")}>SQL</th>
            </tr>
          </thead>
          <tbody>
            {queryOnlyLogs.map((log, idx) => {
              const status = queryStatusLabel(log.status);
              return (
              <tr key={log.query_id ?? `${log.session_id}-${log.ts}-${idx}`} className="align-top transition-colors hover:bg-slate-50/70">
                <td className={cx(TD, "whitespace-nowrap text-slate-500")}>{formatDateTime(log.ts, true) || "—"}</td>
                <td className={cx(TD, "whitespace-nowrap font-medium text-navy")}>{log.user_name}</td>
                <td className={cx(TD, "whitespace-nowrap")}>
                  {log.api_provider ? (
                    <div>
                      <div className="font-medium text-slate-800">{log.api_provider}</div>
                      {log.api_model && <div className="text-[12px] text-slate-400">{log.api_model}</div>}
                    </div>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
                <td className={cx(TD, "min-w-[14rem] max-w-xs text-slate-800")}>
                  <span className="line-clamp-2" title={log.question}>{log.question}</span>
                </td>
                <td className={cx(TD, "whitespace-nowrap")}>
                  <span title={log.error_message || undefined}><Badge tone={status.tone}>{status.label}</Badge></span>
                </td>
                <td className={cx(TD, "whitespace-nowrap")}>
                  {log.feedback_rating === 1 ? (
                    <span className="inline-flex items-center gap-1.5 font-medium text-emerald-700">
                      <IconThumbUp className="h-4 w-4" /> Hài lòng
                    </span>
                  ) : log.feedback_rating === -1 ? (
                    <div>
                      <span className="inline-flex items-center gap-1.5 font-medium text-red-700">
                        <IconThumbDown className="h-4 w-4" /> Không hài lòng
                      </span>
                      {log.feedback_category && (
                        <div className="mt-0.5 text-[12px] text-slate-500">
                          {FEEDBACK_CATEGORY_LABELS[log.feedback_category] || log.feedback_category}
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-slate-400">Chưa đánh giá</span>
                  )}
                </td>
                <td className={cx(TD, "min-w-[12rem] max-w-[16rem] text-slate-600")}>
                  <span className="line-clamp-2" title={log.feedback_comment || undefined}>{log.feedback_comment || "—"}</span>
                </td>
                <td className={cx(TD, "text-right")}>{log.session_input_tokens.toLocaleString("vi-VN")}</td>
                <td className={cx(TD, "text-right")}>{log.session_output_tokens.toLocaleString("vi-VN")}</td>
                <td className={cx(TD, "whitespace-nowrap text-right font-medium text-navy")}>{formatVnd(log.session_cost_vnd)}</td>
                <td className={cx(TD, "whitespace-nowrap text-right text-slate-500")}>
                  {log.duration_ms != null ? (
                    `${(log.duration_ms / 1000).toFixed(1).replace(".", ",")} giây`
                  ) : log.tool_duration_ms != null ? (
                    <span className="text-slate-400" title={`Không có bản ghi cả lượt. Một lần gọi công cụ mất ${log.tool_duration_ms} ms — không phải thời gian trả lời.`}>—</span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className={TD}>
                  {log.sql ? (
                    <details>
                      <summary className="cursor-pointer select-none whitespace-nowrap font-medium text-brand hover:underline">Xem SQL</summary>
                      <pre className="custom-scroll mt-2 max-w-md overflow-x-auto rounded-lg bg-navy p-3 font-mono text-[12px] leading-relaxed text-slate-100">{log.sql}</pre>
                    </details>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </TableCard>
    </div>
  );
}

function WeeklyView({ data, loading, offset, onChangeWeek }: {
  data: WeeklyAuditData | null;
  loading: boolean;
  offset: number;
  onChangeWeek: (offset: number) => void;
}) {
  const days = data?.daily_breakdown || [];
  const maxCost = Math.max(1, ...days.map((d) => d.cost_vnd));
  const providerNames = [...new Set((data?.provider_breakdown || []).map((p) => p.provider))];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <IconButton label="Tuần trước" onClick={() => onChangeWeek(offset - 1)} className="bg-white shadow-card ring-1 ring-inset ring-line">
            <IconChevronLeft className="h-[18px] w-[18px]" />
          </IconButton>
          <IconButton label="Tuần sau" disabled={offset >= 0} onClick={() => onChangeWeek(offset + 1)} className="bg-white shadow-card ring-1 ring-inset ring-line">
            <IconChevronRight className="h-[18px] w-[18px]" />
          </IconButton>
          {offset !== 0 && <Button size="sm" variant="ghost" onClick={() => onChangeWeek(0)}>Về tuần này</Button>}
        </div>
        <div className="flex items-center gap-2 text-[15px] font-semibold text-navy">
          {loading && <span className="h-2 w-2 animate-pulse rounded-full bg-brand" aria-hidden="true" />}
          Tuần {data?.week_label || "…"}
          {data?.is_current_week && <Badge tone="brand">Tuần hiện tại</Badge>}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Chi phí trong tuần" value={formatVnd(data?.total_cost_vnd || 0)} />
        <StatCard label="Chi phí (USD)" value={`$${(data?.total_cost_usd || 0).toFixed(4)}`} />
        <StatCard label="Token" value={(data?.total_tokens || 0).toLocaleString("vi-VN")} />
        <StatCard label="Lượt hỏi" value={(data?.total_queries || 0).toLocaleString("vi-VN")} />
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-card ring-1 ring-inset ring-line">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[14px] font-semibold text-navy">Chi phí theo ngày</h3>
          {/* 17/08/2026: chu giai theo NHA CUNG CAP - mau mang nghia danh tinh (tien chay ve dau); to theo
              "hom nay" thi cung mot nha cung cap lai doi mau tuy ngay. Hom nay nhan ra qua nhan truc duoi. */}
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-slate-500">
            {providerNames.length > 0
              ? providerNames.map((ten) => <Swatch key={ten} color={mauNhaCungCap(ten)} label={ten} />)
              : <Swatch color={mauNhaCungCap("")} label="Chi phí" />}
          </div>
        </div>
        {loading && !data ? (
          <Skeleton className="h-56 rounded-xl" />
        ) : (
          <div className="grid h-56 grid-cols-7 items-end gap-2 sm:gap-4">
            {days.map((day) => {
              const barPct = Math.min(100, Math.round((day.cost_vnd / maxCost) * 100));
              const height = day.cost_vnd > 0 ? Math.max(4, barPct) : 0;
              const providers = day.providers || [];
              return (
                <div key={day.day_index} className="group relative flex h-full flex-col items-center justify-end">
                  <span className={cx("mb-1.5 text-[11.5px] font-medium tabular-nums", day.is_today ? "text-navy" : "text-slate-500")}>
                    {day.cost_vnd > 0 ? compactVnd(day.cost_vnd) : "—"}
                  </span>
                  <div className="flex w-full max-w-[44px] flex-1 flex-col justify-end">
                    {/* Cot xep chong theo nha cung cap, khe 2px de hai mang mau khong dinh thanh mot khoi.
                        Ban ghi cu chua co 'providers' -> mot doan xam, khong vo nhu biet nguon nao. */}
                    {day.cost_vnd > 0 && providers.length > 0 ? (
                      <div style={{ height: `${height}%` }} className="flex w-full flex-col justify-end gap-[2px] transition-all duration-500 ease-out">
                        {providers.map((p, pi) => (
                          <div
                            key={`${p.provider}-${p.api_key_id}-${p.model}`}
                            title={`${p.provider} · ${p.query_count} lượt · ${formatVnd(p.cost_vnd)}`}
                            style={{ height: `${Math.max(3, (p.cost_vnd / day.cost_vnd) * 100)}%`, background: mauNhaCungCap(p.provider) }}
                            className={cx("w-full", pi === 0 && "rounded-t-lg")}
                          />
                        ))}
                      </div>
                    ) : (
                      <div
                        style={{ height: `${height}%`, background: day.query_count > 0 ? MAU_KHAC : "transparent" }}
                        className="w-full rounded-t-lg transition-all duration-500 ease-out"
                      />
                    )}
                    <div className="h-px w-full bg-line" />
                  </div>
                  <span className={cx("mt-2 rounded-md px-1.5 text-[12px] font-medium", day.is_today ? "bg-navy text-white" : "text-slate-700")}>
                    {day.day_name}
                  </span>
                  <span className="text-[11px] tabular-nums text-slate-400">{day.is_today ? "hôm nay" : day.display_date}</span>
                  <div className="pointer-events-none absolute bottom-full z-20 mb-1 hidden w-52 rounded-xl bg-navy p-3 text-[12px] text-white shadow-float group-hover:block">
                    <div className="mb-1.5 font-semibold">{day.day_name}, {day.display_date}{day.is_today ? " · hôm nay" : ""}</div>
                    <div className="flex justify-between tabular-nums text-slate-300"><span>Chi phí</span><span className="text-white">{formatVnd(day.cost_vnd)}</span></div>
                    <div className="flex justify-between tabular-nums text-slate-300"><span>Token</span><span>{day.total_tokens.toLocaleString("vi-VN")}</span></div>
                    <div className="flex justify-between tabular-nums text-slate-300"><span>Lượt hỏi</span><span>{day.query_count}</span></div>
                    {providers.length > 0 && (
                      <div className="mt-1.5 space-y-1 border-t border-white/10 pt-1.5 tabular-nums">
                        {providers.map((p) => (
                          <div key={`tt-${p.provider}-${p.api_key_id}-${p.model}`} className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-1.5 text-slate-300">
                              <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: mauNhaCungCap(p.provider) }} />
                              {p.provider}
                            </span>
                            <span className="whitespace-nowrap text-slate-200">{p.query_count} lượt · {formatVnd(p.cost_vnd)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 17/08/2026: chi phi tach theo NHA CUNG CAP / API KEY - ngay co tu 2 nguon tro len duoc danh dau. */}
      {(data?.provider_breakdown?.length ?? 0) > 0 && (
        <div className="space-y-2.5">
          <h3 className="text-[14px] font-semibold text-navy">Theo nhà cung cấp / API key</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data?.provider_breakdown.map((p) => (
              <div key={`${p.provider}-${p.api_key_id}-${p.model}`} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-inset ring-line">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-2 text-[13.5px] font-medium text-navy">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: mauNhaCungCap(p.provider) }} />
                    {p.provider}
                  </span>
                  <span className="font-mono text-[11.5px] text-slate-400">{p.api_key_id}</span>
                </div>
                <div className="mt-1 text-[12.5px] text-slate-500">{p.model}</div>
                <div className="mt-2 flex items-baseline justify-between tabular-nums">
                  <span className="text-[13px] text-slate-600">{p.query_count.toLocaleString("vi-VN")} lượt</span>
                  <span className="text-[16px] font-semibold text-navy">{formatVnd(p.cost_vnd)}</span>
                </div>
              </div>
            ))}
          </div>
          <TableCard nhan="chi-phi-theo-nha-cung-cap" className="max-h-64">
            <table className="w-full border-collapse text-[13.5px] tabular-nums">
              <thead>
                <tr>
                  <th className={cx(TH, "text-left")}>Ngày</th>
                  <th className={cx(TH, "text-left")}>Nhà cung cấp</th>
                  <th className={cx(TH, "text-left")}>API key</th>
                  <th className={cx(TH, "text-left")}>Model</th>
                  <th className={cx(TH, "text-right")}>Lượt</th>
                  <th className={cx(TH, "text-right")}>Chi phí</th>
                </tr>
              </thead>
              <tbody>
                {days
                  .filter((d) => d.providers && d.providers.length > 0)
                  .flatMap((d) =>
                    d.providers.map((p, pi) => (
                      <tr key={`${d.date_str}-${p.provider}-${p.api_key_id}-${p.model}`} className="transition-colors hover:bg-slate-50/70">
                        <td className={TD}>
                          {pi === 0 ? (
                            <span className="inline-flex items-center gap-2 font-medium text-navy">
                              {d.day_name} {d.display_date}
                              {d.providers.length > 1 && <Badge tone="danger">{d.providers.length} nguồn</Badge>}
                            </span>
                          ) : (
                            <span className="text-slate-300">↳</span>
                          )}
                        </td>
                        <td className={TD}><Swatch color={mauNhaCungCap(p.provider)} label={p.provider} /></td>
                        <td className={cx(TD, "font-mono text-[12px] text-slate-500")}>{p.api_key_id}</td>
                        <td className={cx(TD, "text-slate-600")}>{p.model}</td>
                        <td className={cx(TD, "text-right")}>{p.query_count.toLocaleString("vi-VN")}</td>
                        <td className={cx(TD, "text-right font-semibold text-navy")}>{formatVnd(p.cost_vnd)}</td>
                      </tr>
                    )),
                  )}
              </tbody>
            </table>
          </TableCard>
          <p className="text-[12px] leading-relaxed text-slate-400">
            Nhãn API key chỉ để phân biệt các key với nhau (4 ký tự cuối kèm mã băm), không khôi phục được key. Bản ghi
            trước 17/08 chưa lưu nhãn key nên hiện “(không ghi)”, nhà cung cấp được suy từ tên model.
          </p>
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-[14px] font-semibold text-navy">Theo tài khoản trong tuần</h3>
        <TableCard nhan="chi-phi-tuan-theo-tai-khoan" className="max-h-72">
          <table className="w-full border-collapse text-[13.5px] tabular-nums">
            <thead>
              <tr>
                <th className={cx(TH, "text-left")}>Người dùng</th>
                <th className={cx(TH, "text-left")}>Tài khoản</th>
                <th className={cx(TH, "text-right")}>Số câu hỏi</th>
                <th className={cx(TH, "text-right")}>Tổng token</th>
                <th className={cx(TH, "text-right")}>Chi phí (VNĐ)</th>
              </tr>
            </thead>
            <tbody>
              {data?.user_breakdown.map((u) => (
                <tr key={u.username} className="transition-colors hover:bg-slate-50/70">
                  <td className={cx(TD, "font-medium text-navy")}>{u.user_name}</td>
                  <td className={cx(TD, "font-mono text-[12.5px] text-slate-500")}>{u.username}</td>
                  <td className={cx(TD, "text-right")}>{u.query_count}</td>
                  <td className={cx(TD, "text-right")}>{u.total_tokens.toLocaleString("vi-VN")}</td>
                  <td className={cx(TD, "text-right font-semibold text-navy")}>{formatVnd(u.cost_vnd)}</td>
                </tr>
              ))}
              {(!data || data.user_breakdown.length === 0) && (
                <tr>
                  <td colSpan={5} className="px-3.5 py-8 text-center text-slate-400">Chưa có lượt hỏi nào trong tuần này.</td>
                </tr>
              )}
            </tbody>
          </table>
        </TableCard>
      </div>
    </div>
  );
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}

function compactVnd(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(".", ",")} tr`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return `${value}`;
}
