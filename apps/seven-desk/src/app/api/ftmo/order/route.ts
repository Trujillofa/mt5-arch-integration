import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleLiveOrderPost("ftmo", "/api/ftmo/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/ftmo/order",
      stage: "method",
      reason:
        'GET is read-only. Live FTMO OrderSend requires POST { live: true, confirm: "FTMO-541163357", action: "open" }. Default 1.4 lots (market / limit / stop). volume_min: true is the 0.01 prove.',
      winePrefix: ".mt5-ftmo",
    },
    { status: 405 }
  );
}
