export async function GET(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chưa được cấu hình (BACKEND_API_URL)" }, { status: 500 });
  }

  const { searchParams } = new URL(request.url);
  const weekOffset = searchParams.get("week_offset") || "0";

  const queryParams = new URLSearchParams({ week_offset: weekOffset });

  const authHeader = request.headers.get("authorization");
  const res = await fetch(`${backendUrl}/audit-logs/weekly?${queryParams.toString()}`, {
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
