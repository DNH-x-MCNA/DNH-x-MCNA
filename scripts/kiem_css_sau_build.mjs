// Chay ngay sau `next build` (package.json "build"): lam build THAT BAI khi CSS vua build khong khop
// src/app/globals.css hien tai, de Vercel giu nguyen ban dang chay thay vi len ban hong giao dien.
//
// 28/09/2026: ban deploy #133 phuc vu CSS cu (cua truoc #133) nhung build van "thanh cong" - nut dang
// nhap trong suot, vien va chu nhat tren production. Xem ghi chu trong next.config.ts.
//
// Kiem 2 dieu:
// 1. Moi bien khai bao trong khoi :root cua globals.css deu co trong CSS da build (CSS cu thi thieu bien moi).
// 2. Moi token mau cua @theme inline (--color-X) ma src/app dung truc tiep dang bg-X / text-X / ring-X /
//    border-X (khong kem hover:, focus:...) deu sinh ra rule .bg-X{ ... } tuong ung.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const goc = process.cwd();
const globals = readFileSync(join(goc, "src/app/globals.css"), "utf8");

const khoiRoot = globals.match(/:root\s*\{([\s\S]*?)\}/)?.[1] ?? "";
const bienRoot = [...khoiRoot.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]);
const khoiTheme = globals.match(/@theme\s+inline\s*\{([\s\S]*?)(?:@keyframes|\n\})/)?.[1] ?? "";
const mauTheme = [...khoiTheme.matchAll(/--color-([\w-]+)\s*:/g)].map((m) => m[1]);
if (bienRoot.length === 0 || mauTheme.length === 0) {
  console.error("kiem_css_sau_build: khong doc duoc :root / @theme inline trong src/app/globals.css - sua lai bieu thuc trong script nay.");
  process.exit(1);
}

const thuMucStatic = join(goc, ".next/static");
const css = readdirSync(thuMucStatic, { recursive: true })
  .filter((f) => String(f).endsWith(".css"))
  .map((f) => readFileSync(join(thuMucStatic, String(f)), "utf8"))
  .join("\n");

const thuMucApp = join(goc, "src/app");
const nguon = readdirSync(thuMucApp, { recursive: true })
  .filter((f) => /\.(tsx|ts)$/.test(String(f)))
  .map((f) => readFileSync(join(thuMucApp, String(f)), "utf8"))
  .join("\n");

const thieuBien = bienRoot.filter((b) => !css.includes(`${b}:`));
const thieuTienIch = [];
for (const ten of mauTheme) {
  for (const tienTo of ["bg", "text", "ring", "border"]) {
    const lop = `${tienTo}-${ten}`;
    // Chi xet lop dung truc tiep (dung sau khoang trang/dau nhay), khong xet hover:bg-X...
    const dung = new RegExp(`(?<=[\\s"'\`])${lop}(?![\\w-])`).test(nguon);
    // Lightning CSS gop selector cung khai bao (".bg-soft,.bg-soft\/60{...}") nen tim .X dung truoc "," hoac "{".
    const coRule = new RegExp(`(?:^|[{},\\s])\\.${lop}(?=[,{])`).test(css);
    if (dung && !coRule) thieuTienIch.push(lop);
  }
}

if (thieuBien.length || thieuTienIch.length) {
  console.error("kiem_css_sau_build: CSS vua build KHONG khop src/app/globals.css (co the la CSS cu tu cache).");
  if (thieuBien.length) console.error(`  thieu bien :root: ${thieuBien.join(", ")}`);
  if (thieuTienIch.length) console.error(`  thieu tien ich mau: ${thieuTienIch.join(", ")}`);
  console.error("  Xoa .next roi build lai; tren Vercel: Redeploy, bo chon 'Use existing Build Cache'.");
  process.exit(1);
}
console.log(`kiem_css_sau_build: khop (${bienRoot.length} bien :root, ${mauTheme.length} token mau).`);
