"use client";

import { memo, useEffect, useRef, useState } from "react";
import { AnswerMarkdown, DataTable } from "./AnswerMarkdown";
import { IconCheck, IconCopy, IconDatabase, IconRetry } from "./icons";
import type { Message } from "./lib";
import { Button, Notice, cx } from "./ui";

// Boc React.memo: page.tsx co state `input` doi moi lan go phim; neu khung tin nhan ve lai theo thi
// toan bo markdown/bang cua moi tin nhan cu bi parse lai moi ky tu - cang nhieu tin nhan cang lag.
// Component nay CHI ve lai khi `messages`/`loading` thuc su doi.
export const MessageList = memo(function MessageList({ messages, loading, onRetry }: {
  messages: Message[];
  loading: boolean;
  onRetry: (question: string) => void;
}) {
  return (
    <div className="flex flex-col gap-8">
      {messages.map((m, i) => {
        const isLast = i === messages.length - 1;
        if (m.role === "user") return <UserMessage key={i} text={m.text} />;
        const question = findQuestionBefore(messages, i);
        return (
          <BotMessage
            key={i}
            message={m}
            streaming={loading && isLast}
            onRetry={question && !loading ? () => onRetry(question) : undefined}
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

function BotMessage({ message: m, streaming, onRetry }: {
  message: Message;
  streaming: boolean;
  onRetry?: () => void;
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
            {!streaming && (
              <div className="mt-2 flex flex-wrap items-center gap-1 text-slate-500">
                {/* Chep chu da hien (innerText), khong chep markdown tho: dan vao email khong dinh "**",
                    bang dan vao Excel tu tach dung cot (innerText noi o bang bang tab). */}
                <CopyButton getText={() => contentRef.current?.innerText || m.text} />
                {sqlCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowSql((v) => !v)}
                    aria-expanded={showSql}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium transition hover:bg-sunken hover:text-slate-900"
                  >
                    <IconDatabase className="h-4 w-4" />
                    {showSql ? "Ẩn truy vấn" : `Xem truy vấn đã dùng${sqlCount > 1 ? ` (${sqlCount})` : ""}`}
                  </button>
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
      className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium transition hover:bg-sunken hover:text-slate-900"
    >
      {copied ? <IconCheck className="h-4 w-4 text-emerald-600" /> : <IconCopy className="h-4 w-4" />}
      {copied ? "Đã sao chép" : "Sao chép"}
    </button>
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
