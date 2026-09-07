import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleLiveOrderPost("fundednext", "/api/fundednext/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/fundednext/order",
      stage: "method",
      reason:
        'GET is read-only. Live FundedNext OrderSend requires POST { live: true, confirm: "FN-13981906", action: "open" }. Default 0.35 lots (market / limit / stop). volume_min: true is the 0.01 prove.',
      winePrefix: ".mt5-fundednext",
    },
    { status: 405 }
  );
}
