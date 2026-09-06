import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleLiveOrderPost("fundingpips", "/api/fundingpips/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/fundingpips/order",
      stage: "method",
      reason:
        'GET is read-only. Live FundingPips OrderSend requires POST { live: true, confirm: "FUNDINGPIPS-11669306", action: "open", volume_min: true }.',
      winePrefix: ".mt5-fundingpips",
    },
    { status: 405 }
  );
}
