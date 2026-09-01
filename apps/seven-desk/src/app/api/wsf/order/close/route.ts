import { executeWsfLiveOrder } from "@/lib/wsf/live-order";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 120;

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      {
        ok: false,
        source: "seven-desk",
        endpoint: "/api/wsf/order/close",
        stage: "body",
        reason: "JSON body required",
        winePrefix: ".mt5-wsf",
      },
      { status: 400 }
    );
  }
  const payload = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const { status, result } = await executeWsfLiveOrder(
    {
      live: payload.live,
      confirm: payload.confirm,
      action: "close",
      symbol: payload.symbol,
      side: payload.side,
      volume: payload.volume,
      volume_min: payload.volume_min ?? true,
    },
    "/api/wsf/order/close"
  );
  return Response.json(result, { status });
}
