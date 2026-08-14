import { proxyFetch } from "../../../_proxy";

export async function PUT(request: Request, ctx: { params: Promise<{ queryId: string }> }) {
  const { queryId } = await ctx.params;
  const backendUrl = process.env.BACKEND_API_URL;
  const apiKey = process.env.BACKEND_API_KEY;
  if (!backendUrl) {
    return Response.json({ detail: "Backend chua duoc cau hinh (BACKEND_API_URL)" }, { status: 500 });
  }

  const authHeader = request.headers.get("authorization");
  return proxyFetch(`${backendUrl}/queries/${encodeURIComponent(queryId)}/feedback`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
    body: await request.text(),
  });
}
