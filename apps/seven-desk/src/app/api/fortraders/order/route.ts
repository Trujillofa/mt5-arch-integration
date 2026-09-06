import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleLiveOrderPost("fortraders", "/api/fortraders/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/fortraders/order",
      stage: "method",
      reason:
        'GET is read-only. Live Fortraders OrderSend requires POST { live: true, confirm: "FORTRADERS-737150", action: "open", volume_min: true }.',
      winePrefix: ".mt5-fortraders",
    },
    { status: 405 }
  );
}
