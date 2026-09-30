"use client";

export type ChartSpec = {
  version: 1; kind: "bar" | "line"; title: string; unit: "VND";
  labels: string[]; series: { name: string; values: (number | null)[] }[]; note: string;
};

// API/history payloads are untrusted input. No HTML, scripts, URLs or SVG from the server.
export function parseCharts(value: unknown): ChartSpec[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 3).filter((c): c is ChartSpec => {
    if (!c || c.version !== 1 || !["bar", "line"].includes(c.kind) || c.unit !== "VND") return false;
    if (typeof c.title !== "string" || c.title.length > 160 || typeof c.note !== "string" || c.note.length > 500) return false;
    if (!Array.isArray(c.labels) || !c.labels.length || c.labels.length > 24 ||
        !c.labels.every((l: unknown) => typeof l === "string" && l.length <= 80)) return false;
    return Array.isArray(c.series) && c.series.length > 0 && c.series.length <= 5 && c.series.every((s: ChartSpec["series"][number]) =>
      s && typeof s.name === "string" && s.name.length <= 80 && Array.isArray(s.values) && s.values.length === c.labels.length &&
      s.values.every(v => v === null || (typeof v === "number" && Number.isFinite(v) && Math.abs(v) < 1e18)));
  });
}

const COLORS = ["#0369a1", "#b45309", "#7c3aed", "#047857", "#be123c"];
// Tron toi dong: mac dinh toLocaleString giu 3 so le (du phong tuyen tinh tung hien "21.761.085.237,931 đ").
const full = (v: number | null) => v === null ? "Chưa đủ dữ liệu" : `${v.toLocaleString("vi-VN", { maximumFractionDigits: 0 })} đ`;
const short = (v: number) => Math.abs(v) >= 1e9 ? `${(v / 1e9).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ`
  : Math.abs(v) >= 1e6 ? `${(v / 1e6).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tr`
  : v.toLocaleString("vi-VN", { maximumFractionDigits: 0 });

export function ReportCharts({ charts }: { charts: unknown }) {
  return <>{parseCharts(charts).map((c, i) => <ReportChart key={i} chart={c} />)}</>;
}

function ReportChart({ chart: c }: { chart: ChartSpec }) {
  const values = c.series.flatMap(s => s.values).filter((v): v is number => v !== null);
  if (!values.length) return null;
  const min = Math.min(0, ...values), max = Math.max(0, ...values);
  const range = max - min || 1;
  const bar = c.kind === "bar";
  const height = bar ? Math.max(180, c.labels.length * (c.series.length * 15 + 22) + 42) : 280;
  const x = (v: number) => 135 + (v - min) / range * 470;
  const lineX = (i: number) => 65 + i / Math.max(1, c.labels.length - 1) * 540;
  const lineY = (v: number) => 230 - (v - min) / range * 205;
  return <figure className="my-4 rounded-xl border border-slate-200 bg-white p-3 sm:p-4">
    <figcaption className="font-semibold text-slate-900">{c.title}</figcaption>
    <div className="my-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700">
      {c.series.map((s, i) => <span key={i} className="inline-flex items-center gap-1.5">
        <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ background: COLORS[i] }} />{s.name}
      </span>)}
    </div>
    <div className="overflow-x-auto">
    <svg viewBox={`0 0 640 ${height}`} role="img" aria-label={`${c.title}. Đơn vị đồng; bảng số liệu ở bên dưới.`} className="w-full" style={{ minWidth: 520 }}>
      <title>{c.title}</title>
      {bar ? <>
        {[min, min + range / 2, max].map((v, i) => <g key={i}>
          <line x1={x(v)} x2={x(v)} y1={20} y2={height - 20} stroke="#e2e8f0" />
          <text x={x(v)} y={12} textAnchor="middle" fontSize="10" fill="#475569">{short(v)}</text>
        </g>)}
        {c.labels.map((label, i) => {
          const y = 28 + i * (c.series.length * 15 + 22);
          return <g key={i}>
            <text x={125} y={y + 12} textAnchor="end" fontSize="11" fill="#334155"><title>{label}</title>{label.length > 19 ? `${label.slice(0, 18)}…` : label}</text>
            {c.series.map((s, j) => { const v = s.values[i]; return v === null ? null :
              <rect key={j} x={Math.min(x(0), x(v))} y={y + j * 15} width={Math.max(1, Math.abs(x(v) - x(0)))} height={11} rx={2} fill={COLORS[j]}>
                <title>{`${label} · ${s.name}: ${full(v)}`}</title>
              </rect>; })}
          </g>;
        })}
      </> : <>
        {[min, min + range / 2, max].map((v, i) => <g key={i}>
          <line x1={65} x2={605} y1={lineY(v)} y2={lineY(v)} stroke="#e2e8f0" />
          <text x={60} y={lineY(v) + 4} textAnchor="end" fontSize="10" fill="#475569">{short(v)}</text>
        </g>)}
        {c.labels.map((label, i) => i % Math.ceil(c.labels.length / 6) === 0 || i === c.labels.length - 1 ?
          <text key={i} x={lineX(i)} y={253} textAnchor="middle" fontSize="10" fill="#475569">{label}</text> : null)}
        {c.series.map((s, j) => <g key={j}>
          <path d={s.values.map((v, i) => v === null ? "" : `${i === 0 || s.values[i - 1] === null ? "M" : "L"}${lineX(i)},${lineY(v)}`).join(" ")}
            fill="none" stroke={COLORS[j]} strokeWidth={2.5} />
          {s.values.map((v, i) => v === null ? null : <circle key={i} cx={lineX(i)} cy={lineY(v)} r={3.5} fill={COLORS[j]}>
            <title>{`${c.labels[i]} · ${s.name}: ${full(v)}`}</title>
          </circle>)}
        </g>)}
      </>}
    </svg>
    </div>
    <p className="text-xs leading-5 text-slate-600">{c.note}</p>
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer py-1 font-medium text-sky-800">Xem số liệu biểu đồ</summary>
      <div className="overflow-x-auto"><table className="w-full text-left">
        <thead><tr><th className="p-2">Phạm vi/kỳ</th>{c.series.map((s, i) => <th className="p-2" key={i}>{s.name}</th>)}</tr></thead>
        <tbody>{c.labels.map((l, i) => <tr key={i}><th className="p-2 font-normal">{l}</th>{c.series.map((s, j) => <td className="p-2 whitespace-nowrap" key={j}>{full(s.values[i])}</td>)}</tr>)}</tbody>
      </table></div>
    </details>
  </figure>;
}
