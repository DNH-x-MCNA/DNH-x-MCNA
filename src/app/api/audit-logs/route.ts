export async function GET(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chưa được cấu hình (BACKEND_API_URL)" }, { status: 500 });
  }

  const { searchParams } = new URL(request.url);
  const days = searchParams.get("days") || "30";
  const date = searchParams.get("date") || "";
  const limit = searchParams.get("limit") || "200";
  const userFilter = searchParams.get("user_filter") || "";

  const queryParams = new URLSearchParams({
    limit,
    ...(date ? { date } : { days }),
    ...(userFilter ? { user_filter: userFilter } : {}),
  });

  const authHeader = request.headers.get("authorization");
  const res = await fetch(`${backendUrl}/audit-logs?${queryParams.toString()}`, {
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
