"use client";

// Hien thi cau tra loi cua tro ly: markdown (bang, danh sach, in dam) + bang du lieu co cau truc tu SQL.
// Tach tu page.tsx 28/09/2026 khi thiet ke lai; quy tac can cot so va tag kenh/vung giu nguyen.
import { CSSProperties, ReactNode, memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Tag mau co dinh cho ky hieu kenh/vung xuat hien DUNG NGUYEN VAN trong 1 o bang - chi khop chinh
// xac (sau khi trim), KHONG doan/parse noi dung cau tra loi cua AI nen khong co rui ro hien sai so
// lieu. Cell nao khong khop 1 trong cac khoa nay se render binh thuong nhu truoc.
const CHANNEL_REGION_TAG_STYLES: Record<string, string> = {
  ETC: "bg-indigo-50 text-indigo-700",
  OTC: "bg-sky-50 text-sky-700",
  "Miền Bắc": "bg-blue-50 text-blue-700",
  "Miền Nam": "bg-emerald-50 text-emerald-700",
  "Miền Trung": "bg-amber-50 text-amber-800",
};

function Tag({ text, className }: { text: string; className: string }) {
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[12px] font-medium ${className}`}>{text}</span>;
}

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
// COT thay vi tung o rieng le vi o day co du lieu goc (number hoac string) nen do tin cay cao hon.
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
// <td> rieng le. Ly do: can-phai tung o khien tieu de cot ("Doanh thu") nam ben trai trong khi so
// lieu ben duoi nam ben phai - nhin giong bi lech hang du moi o rieng le van dung. Ap dung style
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

const TABLE_WRAP = "custom-scroll my-4 overflow-x-auto rounded-xl ring-1 ring-inset ring-line";
const TH = "whitespace-nowrap border-b border-line bg-soft px-3.5 py-2.5 text-[12.5px] font-medium text-slate-500";
const TD = "border-b border-slate-100 px-3.5 py-2.5 align-top text-slate-800";

// Style rieng cho tung the markdown trong cau tra loi (bang, in dam, danh sach...)
const markdownComponents = {
  p: ({ children }: { children?: ReactNode }) => <p className="my-3 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }: { children?: ReactNode }) => <strong className="font-semibold text-navy">{children}</strong>,
  em: ({ children }: { children?: ReactNode }) => <em className="text-slate-500">{children}</em>,
  a: ({ children, href }: { children?: ReactNode; href?: string }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium text-brand underline decoration-indigo-200 underline-offset-2 hover:decoration-brand">
      {children}
    </a>
  ),
  ul: ({ children }: { children?: ReactNode }) => <ul className="my-3 list-disc space-y-1.5 pl-5 marker:text-slate-300 last:mb-0">{children}</ul>,
  ol: ({ children }: { children?: ReactNode }) => <ol className="my-3 list-decimal space-y-1.5 pl-5 marker:text-slate-400 last:mb-0">{children}</ol>,
  li: ({ children }: { children?: ReactNode }) => <li className="pl-1">{children}</li>,
  h1: ({ children }: { children?: ReactNode }) => <h3 className="mb-2 mt-5 text-[17px] font-semibold tracking-tight text-navy first:mt-0">{children}</h3>,
  h2: ({ children }: { children?: ReactNode }) => <h3 className="mb-2 mt-5 text-[16px] font-semibold tracking-tight text-navy first:mt-0">{children}</h3>,
  h3: ({ children }: { children?: ReactNode }) => <h4 className="mb-1.5 mt-4 text-[15px] font-semibold text-navy first:mt-0">{children}</h4>,
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-3 border-l-2 border-line-strong pl-4 text-slate-600">{children}</blockquote>
  ),
  code: ({ children }: { children?: ReactNode }) => (
    <code className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[0.85em] text-slate-800">{children}</code>
  ),
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="custom-scroll my-3 overflow-x-auto rounded-xl bg-soft p-4 text-[13px] leading-relaxed ring-1 ring-inset ring-line [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  hr: () => <hr className="my-5 border-line" />,
  table: ({ children }: { children?: ReactNode }) => (
    <div className={TABLE_WRAP}>
      <table className="w-full border-collapse text-[13.5px] tabular-nums [&_tbody_tr:last-child_td]:border-b-0">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => <thead>{children}</thead>,
  tbody: ({ children }: { children?: ReactNode }) => <tbody className="bg-white">{children}</tbody>,
  tr: ({ children }: { children?: ReactNode }) => <tr className="transition-colors hover:bg-slate-50/70">{children}</tr>,
  // mdast-util-to-hast tao thuoc tinh HAST "align" (cu) tu truong "align" cua mdast ma
  // remarkAlignNumericColumns gan (xet CA COT). react-markdown roi chuyen thuoc tinh HAST "align" do
  // THANH prop `style={{textAlign}}` khi tao React element - da xac minh bang render thu - phai nhan
  // `style`, khong duoc chi destructure {children} roi bo qua, neu khong tieu de cot se khong can
  // theo du lieu ben duoi.
  th: ({ children, style }: { children?: ReactNode; style?: CSSProperties }) => (
    <th className={`${TH} ${style?.textAlign === "right" ? "text-right" : "text-left"}`}>{children}</th>
  ),
  // Tag mau cho o chi chua dung 1 khoa kenh/vung - chi ap dung khi getPlainCellText tra ve chuoi
  // thuan (khong co the long ben trong), neu khong khop thi giu nguyen cach render mac dinh.
  td: ({ children, style }: { children?: ReactNode; style?: CSSProperties }) => {
    const trimmed = getPlainCellText(children)?.trim();
    const tagClass = trimmed ? CHANNEL_REGION_TAG_STYLES[trimmed] : undefined;
    if (tagClass && trimmed) {
      return <td className={TD}><Tag text={trimmed} className={tagClass} /></td>;
    }
    return <td className={`${TD} ${style?.textAlign === "right" ? "text-right" : "text-left"}`}>{children}</td>;
  },
};

const REMARK_PLUGINS = [remarkGfm, remarkAlignNumericColumns];

export const AnswerMarkdown = memo(function AnswerMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={markdownComponents}>
      {text}
    </ReactMarkdown>
  );
});

/** Bang du lieu co cau truc (cot/dong tra ve thang tu truy van, khong qua chu AI). */
export function DataTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  const numericCols = numericColumnFlags(rows, columns.length);
  return (
    <div className={`${TABLE_WRAP} max-h-[480px]`}>
      <table className="w-full border-collapse text-[13.5px] tabular-nums [&_tbody_tr:last-child_td]:border-b-0">
        <thead className="sticky top-0 z-10">
          <tr>
            {columns.map((c, ci) => (
              <th key={`${c}-${ci}`} className={`${TH} ${numericCols[ci] ? "text-right" : "text-left"}`}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white">
          {rows.map((row, ri) => (
            <tr key={ri} className="transition-colors hover:bg-slate-50/70">
              {row.map((cell, ci) => {
                const cellText = cell === null ? "—" : String(cell);
                const tagClass = CHANNEL_REGION_TAG_STYLES[cellText];
                return (
                  <td key={ci} className={`${TD} ${!tagClass && numericCols[ci] ? "text-right" : "text-left"}`}>
                    {tagClass ? <Tag text={cellText} className={tagClass} /> : cellText}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
