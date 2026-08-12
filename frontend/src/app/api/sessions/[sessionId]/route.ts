export async function DELETE(request: Request, ctx: RouteContext<"/api/sessions/[sessionId]">) {
  const { sessionId } = await ctx.params;
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const authHeader = request.headers.get("authorization");
  const res = await fetch(`${backendUrl}/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
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
