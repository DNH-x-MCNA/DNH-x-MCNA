import { proxyFetch } from "../../_proxy";

export async function GET(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const { searchParams } = new URL(request.url);
  const statusParam = searchParams.get("status");
  const authHeader = request.headers.get("Authorization");

  const url = `${backendUrl}/admin/users` + (statusParam ? `?status=${encodeURIComponent(statusParam)}` : "");
  return proxyFetch(url, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { "Authorization": authHeader } : {}),
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
  });
}
