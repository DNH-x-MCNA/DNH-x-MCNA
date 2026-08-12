import { proxyFetch } from "../_proxy";

// Proxy server-side sang backend FastAPI - giu BACKEND_API_URL/BACKEND_API_KEY tren server, KHONG
// bao gio gui ve trinh duyet (khac voi bien NEXT_PUBLIC_* se bi nhung vao JS bundle phia client).
export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const body = await request.text();
  const authHeader = request.headers.get("authorization");
  return proxyFetch(`${backendUrl}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
    body,
  });
}
