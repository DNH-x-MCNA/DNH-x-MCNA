/**
 * Goi backend FastAPI va LUON tra ve JSON hop le cho trinh duyet.
 *
 * 10/08/2026 - VA LOI "Failed to execute 'json' on 'Response': Unexpected end of JSON input"
 * gap tren man hinh dang nhap that. Truoc do MOI route trong src/app/api deu lam:
 *
 *     const res = await fetch(...);              // KHONG co try/catch
 *     const data = await res.text();
 *     return new Response(data, { headers: { "Content-Type": "application/json" } });
 *
 * Hai loi trong doan do, deu dan toi cung mot trieu chung kho hieu:
 *
 *  1. `fetch` khong duoc bao try/catch. Khi backend khong tra loi (dich vu chet, tunnel dut,
 *     sai host) thi fetch NEM loi -> route crash -> Vercel tra ve body RONG -> phia trinh duyet
 *     goi `response.json()` va bao "Unexpected end of JSON input".
 *  2. Body cua backend duoc dan nhan "application/json" VO DIEU KIEN - ke ca khi body rong,
 *     hoac la trang loi HTML cua proxy/tunnel (502/504). Trinh duyet tin nhan Content-Type roi
 *     parse that bai.
 *
 * Hau qua nghiep vu: nguoi dung thay mot thong bao khong noi len dieu gi, rat de hieu nham la
 * "sai mat khau" trong khi that ra backend dang chet. Nay moi truong hop deu tra JSON co truong
 * `detail` doc duoc, dung dinh dang loi ma backend FastAPI van dung.
 */
export async function proxyFetch(url: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    return Response.json(
      {
        detail:
          "Khong ket noi duoc may chu backend. Kiem tra dich vu backend con chay va " +
          `BACKEND_API_URL co dung khong. (Chi tiet: ${reason})`,
      },
      { status: 502 },
    );
  }

  // 204/205 theo chuan HTTP la KHONG co body - tra thang, khong coi la loi.
  if (res.status === 204 || res.status === 205) {
    return new Response(null, { status: res.status });
  }

  const body = await res.text();

  if (!body.trim()) {
    return Response.json(
      { detail: `May chu backend tra ve body rong (HTTP ${res.status}).` },
      { status: res.status >= 400 ? res.status : 502 },
    );
  }

  // Body co noi dung nhung khong phai JSON: thuong la trang loi HTML cua tunnel/reverse proxy.
  // Khong dan nhan JSON cho no nua - doi thanh JSON co `detail` de UI hien duoc.
  try {
    JSON.parse(body);
  } catch {
    return Response.json(
      {
        detail:
          `May chu backend tra ve du lieu khong phai JSON (HTTP ${res.status}). ` +
          "Nhieu kha nang la trang loi cua reverse proxy/tunnel dung giua.",
      },
      { status: res.status >= 400 ? res.status : 502 },
    );
  }

  return new Response(body, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * IP that cua nguoi dung cho backend gioi han dang nhap / quen mat khau theo tung may.
 *
 * 29/09/2026: backend nam sau Cloudflare tunnel, nen IP no tu thay la IP may chu Vercel - ca cong ty
 * dung chung, 30 lan sai tu bat ky ai la khoa dang nhap cua moi nguoi. Vercel tu ghi de x-real-ip /
 * x-forwarded-for bang IP ket noi that (trinh duyet khong gia duoc). Backend chi tin header nay khi
 * request mang dung X-API-Key, tuc la di qua chinh route nay.
 */
export function clientIpHeaders(request: Request): Record<string, string> {
  const ip = (request.headers.get("x-real-ip") || request.headers.get("x-forwarded-for")?.split(",")[0] || "").trim();
  return ip ? { "X-DNH-Client-IP": ip } : {};
}
