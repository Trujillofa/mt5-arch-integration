import { executeWsfLiveOrder } from "@/lib/wsf/live-order";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 180;

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      {
        ok: false,
        source: "seven-desk",
        endpoint: "/api/wsf/order",
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
      action: payload.action,
      symbol: payload.symbol,
      side: payload.side,
      volume: payload.volume,
      volume_min: payload.volume_min,
    },
    "/api/wsf/order"
  );
  return Response.json(result, { status });
}

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/wsf/order",
      stage: "method",
      reason:
        "GET is read-only. Live WSF OrderSend requires POST { live: true, confirm: \"WSF-149736\", action: \"scratch\", volume_min: true }.",
      winePrefix: ".mt5-wsf",
    },
    { status: 405 }
  );
}
