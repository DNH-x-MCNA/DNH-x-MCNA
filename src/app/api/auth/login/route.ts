export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const body = await request.text();
  const res = await fetch(`${backendUrl}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
    body,
  });

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
