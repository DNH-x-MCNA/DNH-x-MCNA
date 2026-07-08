export async function GET(_request: Request, ctx: RouteContext<"/api/history/[sessionId]">) {
  const { sessionId } = await ctx.params;
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const res = await fetch(`${backendUrl}/history/${encodeURIComponent(sessionId)}`, {
    headers: apiKey ? { "X-API-Key": apiKey } : {},
  });

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
