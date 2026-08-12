// 11/08/2026: proxy RIENG cho /chat/stream (SSE) - KHONG dung chung proxyFetch() (../_proxy.ts) vi
// ham do dung `await res.text()` de doc HET body backend truoc khi tra ve trinh duyet (can thiet
// cho /chat thuong de bat loi HTML/rong tu tunnel), nhung lam vay se BUFFER TOAN BO stream lai roi
// moi gui 1 cuc - pha vo dung muc dich streaming (nguoi dung van thay man hinh trang cho den khi
// backend goi xong het, y het /chat cu). Route nay pipe THANG body cua backend (ReadableStream)
// sang trinh duyet, khong doc/buffer truoc.
export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const body = await request.text();
  const authHeader = request.headers.get("authorization");

  let res: Response;
  try {
    res = await fetch(`${backendUrl}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { "X-API-Key": apiKey } : {}),
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body,
    });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    // Loi ket noi truoc ca khi co response (tunnel dut/backend chet) - client (page.tsx) doc SSE
    // nen tra ve 1 event "error" dung format SSE thay vi JSON thuong, de logic doc stream o
    // frontend xu ly duoc dong nhat (khong can nhanh rieng cho loi tang proxy).
    const errEvent = `data: ${JSON.stringify({
      type: "error",
      message: `Khong ket noi duoc may chu backend. (Chi tiet: ${reason})`,
    })}\n\n`;
    return new Response(errEvent, {
      status: 502,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  if (!res.ok || !res.body) {
    // Backend tra loi nhung KHONG OK (vd 401/403/500 truoc khi kip stream gi, hoac 530 cua
    // tunnel/reverse proxy - trang HTML, khong phai SSE that) - doc noi dung (thuong ngan, JSON
    // loi tu FastAPI HTTPException) va boc lai thanh 1 event SSE duy nhat.
    const text = await res.text().catch(() => "");
    let message = `May chu backend tra ve loi (HTTP ${res.status}).`;
    try {
      const parsed = JSON.parse(text);
      if (parsed?.detail) message = parsed.detail;
    } catch {
      // Body khong phai JSON (vd trang HTML loi cua tunnel/reverse proxy dung giua, giong 530
      // tung gap o /chat thuong) - giu message mac dinh o tren, KHONG lo trang HTML tho ra UI.
    }
    const errEvent = `data: ${JSON.stringify({ type: "error", message })}\n\n`;
    return new Response(errEvent, {
      status: res.status >= 400 ? res.status : 502,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  // Backend OK va co body dang stream - pipe THANG, khong doc/buffer.
  return new Response(res.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
