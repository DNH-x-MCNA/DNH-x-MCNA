export async function GET(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const authHeader = request.headers.get("authorization");
  const res = await fetch(`${backendUrl}/auth/me`, {
    headers: {
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
  });

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
