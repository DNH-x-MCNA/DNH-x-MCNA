"use client";

import { ReactNode, useRef, useState } from "react";

/**
 * Xuất bảng ra file CSV mở được bằng Excel.
 *
 * Hai quyết định dễ gây khó chịu nếu làm sai, ghi lại để người sau khỏi phải đoán:
 *
 * 1) DẤU PHÂN CÁCH — dùng chấm phẩy, không phải dấu phẩy.
 *    Excel tách cột theo "list separator" của Windows. Máy cài vùng Việt Nam mặc định dùng dấu
 *    CHẤM PHẨY, nên file phân cách bằng dấu phẩy khi double-click sẽ dồn hết vào cột A. Mà số
 *    tiền trong báo cáo lại đầy dấu phẩy ngăn nghìn ("1,330,072,584") nên lỗi này chắc chắn xảy
 *    ra chứ không phải hiếm gặp. Máy cài vùng Anh/Mỹ thì ngược lại — đổi hằng số dưới đây là xong.
 *
 * 2) BOM UTF-8 — bắt buộc.
 *    Thiếu 3 byte mở đầu này, Excel đọc file theo bảng mã ANSI và mọi chữ có dấu thành ký tự lạ
 *    ("Miền Bắc" -> "Miá»n Báº¯c"). Trình soạn thảo khác vẫn hiển thị đúng nên rất dễ tưởng là ổn.
 *
 * Nội dung xuất ra ĐÚNG NHƯ ĐANG HIỂN THỊ, không tự ý bỏ dấu ngăn nghìn hay đổi định dạng số.
 * Cố "giúp" ở bước này là sửa dữ liệu sau lưng người dùng.
 */
const CSV_DELIMITER = ";";

/** Đọc thẳng từ DOM nên dùng chung được cho mọi bảng, bất kể do markdown hay React dựng ra. */
export function tableToCsv(root: HTMLElement): string {
  const table = root.tagName === "TABLE" ? root : root.querySelector("table");
  if (!table) return "";

  return Array.from(table.querySelectorAll("tr"))
    .map((tr) =>
      Array.from(tr.querySelectorAll("th,td"))
        .map((cell) => {
          const text = (cell as HTMLElement).innerText.replace(/\s+/g, " ").trim();
          // RFC 4180: chỉ bọc nháy khi cần, và nháy đôi bên trong phải nhân đôi
          const canBoc = text.includes(CSV_DELIMITER) || text.includes('"') || /[\r\n]/.test(text);
          return canBoc ? `"${text.replace(/"/g, '""')}"` : text;
        })
        .join(CSV_DELIMITER)
    )
    .join("\r\n");
}

function tenFile(nhan: string): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${nhan}-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.csv`;
}

function taiVe(csv: string, nhan: string) {
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = tenFile(nhan);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Thu hồi ngay sẽ huỷ file trước khi trình duyệt kịp ghi (Safari), lùi 1 nhịp cho chắc.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportableTable({
  children,
  nhan,
  className = "",
  wrapperClassName = "",
}: {
  children?: ReactNode;
  /** Phần đầu tên file, không dấu, không khoảng trắng. Ví dụ "bang-tra-loi". */
  nhan: string;
  /** Class cho khung cuộn bọc bảng. */
  className?: string;
  /** Class cho khối ngoài cùng (lề trên/dưới). */
  wrapperClassName?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [daTai, setDaTai] = useState(false);

  const xuatFile = () => {
    if (!ref.current) return;
    const csv = tableToCsv(ref.current);
    if (!csv) return;
    taiVe(csv, nhan);
    setDaTai(true);
    setTimeout(() => setDaTai(false), 2000);
  };

  return (
    <div className={wrapperClassName}>
      <div className="mb-1 flex justify-end">
        <button
          type="button"
          onClick={xuatFile}
          aria-label="Tải bảng này về máy dưới dạng file CSV mở được bằng Excel"
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1
                     text-[11px] font-semibold text-slate-600 shadow-sm transition
                     hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800
                     focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
                     focus-visible:outline-blue-600"
        >
          {daTai ? (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
                   strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Đã tải
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                   strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Tải Excel
            </>
          )}
        </button>
      </div>
      <div ref={ref} className={className}>
        {children}
      </div>
    </div>
  );
}
