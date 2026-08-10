import { proxyFetch } from "../../../_proxy";

export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const authHeader = request.headers.get("Authorization");
  const body = await request.text();

  return proxyFetch(`${backendUrl}/admin/users/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { "Authorization": authHeader } : {}),
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
    body,
  });
}
