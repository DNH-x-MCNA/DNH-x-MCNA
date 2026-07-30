export async function POST(
  request: Request,
  { params }: { params: Promise<{ username: string }> }
) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const resolvedParams = await params;
  const username = resolvedParams.username;
  const authHeader = request.headers.get("Authorization");

  const res = await fetch(`${backendUrl}/admin/users/${encodeURIComponent(username)}/toggle-active`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { "Authorization": authHeader } : {}),
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
  });

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
