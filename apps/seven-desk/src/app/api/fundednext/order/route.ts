import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 120;

export const POST = handleLiveOrderPost("fundednext", "/api/fundednext/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/fundednext/order",
      stage: "method",
      reason:
        'GET is read-only. Live FundedNext OrderSend requires POST { live: true, confirm: "FN-13981906", action: "open", volume_min: true }.',
      winePrefix: ".mt5-fundednext",
    },
    { status: 405 }
  );
}
