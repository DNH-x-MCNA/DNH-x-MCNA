"use client";

import { memo, useEffect, useRef, useState } from "react";
import { AnswerMarkdown, DataTable } from "./AnswerMarkdown";
import { IconCheck, IconCopy, IconDatabase, IconRetry, IconThumbDown, IconThumbUp, IconWarning } from "./icons";
import {
  FEEDBACK_CATEGORY_OPTIONS, FeedbackRating, FreshnessItem, Message, SubmitFeedback, formatDateTime,
} from "./lib";
import { Button, Notice, Select, cx } from "./ui";

// Boc React.memo: page.tsx co state `input` doi moi lan go phim; neu khung tin nhan ve lai theo thi
// toan bo markdown/bang cua moi tin nhan cu bi parse lai moi ky tu - cang nhieu tin nhan cang lag.
// Component nay CHI ve lai khi `messages`/`loading` thuc su doi.
export const MessageList = memo(function MessageList({ messages, loading, onRetry, onFeedback }: {
  messages: Message[];
  loading: boolean;
  onRetry: (question: string) => void;
  onFeedback: SubmitFeedback;
}) {
  return (
    <div className="flex flex-col gap-8">
      {messages.map((m, i) => {
        const key = m.id ?? m.queryId ?? i;
        const isLast = i === messages.length - 1;
        if (m.role === "user") return <UserMessage key={key} text={m.text} />;
        const question = findQuestionBefore(messages, i);
        return (
          <BotMessage
            key={key}
            message={m}
            streaming={loading && isLast}
            onRetry={question && !loading ? () => onRetry(question) : undefined}
            onFeedback={onFeedback}
          />
        );
      })}
    </div>
  );
});

function findQuestionBefore(messages: Message[], index: number): string | null {
  for (let j = index - 1; j >= 0; j--) {
    if (messages[j].role === "user") return messages[j].text;
  }
  return null;
}

function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex animate-rise-in justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-sunken px-4 py-2.5 text-[15px] leading-relaxed text-navy sm:max-w-[75%]">
        {text}
      </div>
    </div>
  );
}

function AssistantMark() {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/namha-mark.png" alt="" aria-hidden="true" className="mt-0.5 h-7 w-7 shrink-0 select-none" />;
}

const ACTION = "inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium transition hover:bg-sunken hover:text-slate-900";

function BotMessage({ message: m, streaming, onRetry, onFeedback }: {
  message: Message;
  streaming: boolean;
  onRetry?: () => void;
  onFeedback: SubmitFeedback;
}) {
  const [showSql, setShowSql] = useState(false);
  const sqlRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (showSql) sqlRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [showSql]);
  const waiting = streaming && !m.text;
  const hasTable = Boolean(m.rows && m.columns && m.rows.length > 0);
  const sqlCount = m.sqlUsed?.length || 0;

  // Chep chu da hien (innerText), khong chep markdown tho: dan vao email khong dinh "**", bang dan vao
  // Excel tu tach dung cot. An tam nut "Tai Excel" (data-copy-ignore) de chu cua nut khong lan vao.
  function visibleText(): string {
    const el = contentRef.current;
    if (!el) return m.text;
    const skip = Array.from(el.querySelectorAll<HTMLElement>("[data-copy-ignore]"));
    skip.forEach((node) => (node.style.display = "none"));
    const text = el.innerText;
    skip.forEach((node) => (node.style.display = ""));
    return text || m.text;
  }

  return (
    <div className="flex animate-rise-in gap-3.5">
      <AssistantMark />
      <div className="min-w-0 flex-1 pt-0.5">
        {waiting ? (
          <ThinkingIndicator />
        ) : m.error || m.cancelled ? (
          <Notice
            tone={m.cancelled ? "info" : "danger"}
            title={m.cancelled ? "Đã dừng theo yêu cầu" : "Chưa trả lời được câu hỏi này"}
            action={onRetry && (
              <Button size="sm" variant="secondary" icon={<IconRetry className="h-3.5 w-3.5" />} onClick={onRetry}>
                {m.cancelled ? "Hỏi lại" : "Thử lại"}
              </Button>
            )}
          >
            {m.cancelled ? "Câu trả lời đã bị dừng trước khi hoàn tất." : m.text}
          </Notice>
        ) : (
          <>
            <div ref={contentRef}>
              <div className={cx("break-words text-[15px] leading-7 text-slate-800", streaming && "streaming-caret")}>
                <AnswerMarkdown text={m.text} />
              </div>
              {hasTable && <DataTable columns={m.columns as string[]} rows={m.rows as unknown[][]} />}
            </div>
            {m.freshness && m.freshness.length > 0 && <FreshnessLine items={m.freshness} />}
            {!streaming && (
              <div className="mt-2 flex flex-wrap items-center gap-1 text-slate-500">
                <CopyButton getText={visibleText} />
                {sqlCount > 0 && (
                  <button type="button" onClick={() => setShowSql((v) => !v)} aria-expanded={showSql} className={ACTION}>
                    <IconDatabase className="h-4 w-4" />
                    {showSql ? "Ẩn truy vấn" : `Xem truy vấn đã dùng${sqlCount > 1 ? ` (${sqlCount})` : ""}`}
                  </button>
                )}
                {m.queryId && (
                  <FeedbackControls
                    key={m.queryId}
                    queryId={m.queryId}
                    initialRating={m.feedbackRating}
                    initialCategory={m.feedbackCategory}
                    initialComment={m.feedbackComment}
                    onFeedback={onFeedback}
                  />
                )}
              </div>
            )}
            {showSql && m.sqlUsed && (
              <div ref={sqlRef} className="mt-2 scroll-mb-6 space-y-2">
                <p className="text-[12.5px] text-slate-500">Các truy vấn trợ lý đã chạy để lấy số liệu — dùng để đối chiếu khi cần.</p>
                {m.sqlUsed.map((sql, si) => (
                  <pre key={si} className="custom-scroll overflow-x-auto rounded-xl bg-navy p-4 font-mono text-[12.5px] leading-relaxed text-slate-100">
                    {sql}
                  </pre>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// Moc du lieu backend tra rieng (truong `freshness`): nguoi doc biet so lieu tinh den luc nao, lech la
// do kho chua dong bo kip hay do tinh sai. Nguon cu -> doi mau canh bao.
function FreshnessLine({ items }: { items: FreshnessItem[] }) {
  const dates = items.map((f) => f.business_data_date || f.snapshot_date).filter(Boolean) as string[];
  const synced = items.map((f) => f.sync_completed_at).filter(Boolean) as string[];
  const stale = items.filter((f) => f.is_stale);
  const sources = items.map((f) => f.source_name).filter(Boolean).join(", ");
  const parts = [
    dates.length ? `Dữ liệu đến ${formatDateTime([...dates].sort().slice(-1)[0])}` : null,
    synced.length ? `Đồng bộ ${formatDateTime([...synced].sort().slice(-1)[0])}` : null,
    sources ? `Nguồn: ${sources}` : null,
    stale.length ? stale[0].warning || "nguồn có thể chưa đồng bộ kịp" : null,
  ].filter(Boolean);
  return (
    <p className={cx("mt-3 flex items-start gap-1.5 text-[12.5px] leading-relaxed", stale.length ? "text-amber-700" : "text-slate-400")}>
      {stale.length > 0 && <IconWarning className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
      <span>{parts.join(" · ")}</span>
    </p>
  );
}

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(getText()).then(() => setCopied(true)).catch(() => {});
      }}
      className={ACTION}
    >
      {copied ? <IconCheck className="h-4 w-4 text-emerald-600" /> : <IconCopy className="h-4 w-4" />}
      {copied ? "Đã sao chép" : "Sao chép"}
    </button>
  );
}

const TEXTAREA =
  "block w-full resize-y rounded-xl bg-white px-3.5 py-2.5 text-[14px] text-slate-900 ring-1 ring-inset ring-line-strong " +
  "placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand";

// Danh gia cau tra loi (PUT /api/queries/{id}/feedback). Hai long: luu ngay. Chua hai long: bat chon
// ly do truoc khi luu - doi du an can biet sai o dau (so lieu, pham vi, hieu cau hoi...).
function FeedbackControls({ queryId, initialRating, initialCategory, initialComment, onFeedback }: {
  queryId: string;
  initialRating?: FeedbackRating | null;
  initialCategory?: string | null;
  initialComment?: string | null;
  onFeedback: SubmitFeedback;
}) {
  const [selected, setSelected] = useState<FeedbackRating | null>(initialRating ?? null);
  const [category, setCategory] = useState(initialCategory ?? "");
  const [comment, setComment] = useState(initialComment ?? "");
  const [expanded, setExpanded] = useState(Boolean(initialComment) || initialRating === -1);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"saved" | "error" | null>(null);
  const [errorText, setErrorText] = useState("");

  async function chooseSatisfied() {
    if (selected === 1) {
      setExpanded((value) => !value);
      return;
    }
    setSaving(true);
    setStatus(null);
    setErrorText("");
    try {
      await onFeedback(queryId, 1, undefined, "");
      setSelected(1);
      setCategory("");
      setComment("");
      setExpanded(false);
      setStatus("saved");
    } catch (error) {
      setStatus("error");
      setErrorText((error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function chooseDissatisfied() {
    setSelected(-1);
    setExpanded(true);
    setStatus(null);
    setErrorText("");
  }

  async function saveDetails() {
    if (!selected) return;
    if (selected === -1 && !category) {
      setStatus("error");
      setErrorText("Vui lòng chọn lý do chưa hài lòng.");
      return;
    }
    setSaving(true);
    setStatus(null);
    setErrorText("");
    try {
      await onFeedback(queryId, selected, selected === -1 ? category : undefined, comment);
      setStatus("saved");
    } catch (error) {
      setStatus("error");
      setErrorText((error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const toggle = (active: boolean, tone: "good" | "bad") =>
    cx(
      "inline-flex h-8 w-8 items-center justify-center rounded-lg transition disabled:cursor-wait disabled:opacity-50",
      active
        ? tone === "good" ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"
        : "hover:bg-sunken hover:text-slate-900",
    );

  return (
    <>
      <div className="ml-auto flex items-center gap-1">
        <span className={cx("mr-1 text-[12.5px]", status === "saved" ? "font-medium text-emerald-600" : "hidden text-slate-400 sm:inline")}>
          {status === "saved" ? "Đã lưu đánh giá" : "Câu trả lời có hữu ích?"}
        </span>
        <button type="button" onClick={chooseSatisfied} disabled={saving} aria-label="Hài lòng" title="Hài lòng"
          aria-pressed={selected === 1} className={toggle(selected === 1, "good")}>
          <IconThumbUp className="h-[18px] w-[18px]" />
        </button>
        <button type="button" onClick={chooseDissatisfied} disabled={saving} aria-label="Không hài lòng" title="Không hài lòng"
          aria-pressed={selected === -1} className={toggle(selected === -1, "bad")}>
          <IconThumbDown className="h-[18px] w-[18px]" />
        </button>
        {selected === 1 && (
          <button type="button" onClick={() => setExpanded((value) => !value)} className={ACTION}>
            {expanded ? "Ẩn nhận xét" : initialComment ? "Sửa nhận xét" : "Thêm nhận xét"}
          </button>
        )}
      </div>

      {expanded && selected && (
        <div className="mt-2 basis-full animate-rise-in space-y-2.5 rounded-2xl bg-soft p-3.5 ring-1 ring-inset ring-line">
          {selected === -1 && (
            <Select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Lý do không hài lòng">
              <option value="">Chọn lý do chưa hài lòng…</option>
              {FEEDBACK_CATEGORY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </Select>
          )}
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value.slice(0, 2000))}
            rows={3}
            aria-label="Nhận xét thêm"
            placeholder="Nhận xét thêm để đội dự án kiểm tra (không bắt buộc)"
            className={TEXTAREA}
          />
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] tabular-nums text-slate-400">{comment.length}/2000</span>
            <Button size="sm" variant="primary" loading={saving} onClick={saveDetails}>Gửi đánh giá</Button>
          </div>
        </div>
      )}
      {status === "error" && (
        <p className="basis-full pt-1 text-[12.5px] text-red-600">{errorText || "Không lưu được đánh giá."}</p>
      )}
    </>
  );
}

// Dem giay trong luc cho: mot cau hoi co the mat 30-90 giay (model suy luan + goi nhieu tool), dong
// ho cho nguoi hoi biet he thong van dang chay chu khong bi treo. Component rieng de nhip 1 giay
// khong lam ve lai ca danh sach tin nhan.
function ThinkingIndicator() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="flex h-7 items-center gap-3 text-[14px] text-slate-500" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        <span className="typing-dot h-1.5 w-1.5 rounded-full bg-brand" />
        <span className="typing-dot h-1.5 w-1.5 rounded-full bg-brand [animation-delay:0.15s]" />
        <span className="typing-dot h-1.5 w-1.5 rounded-full bg-brand [animation-delay:0.3s]" />
      </span>
      <span>Đang phân tích dữ liệu</span>
      {seconds >= 3 && <span className="tabular-nums text-slate-400">{seconds} giây</span>}
    </div>
  );
}
