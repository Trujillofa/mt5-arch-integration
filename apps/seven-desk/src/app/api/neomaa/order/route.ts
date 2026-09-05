import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 180;

export const POST = handleLiveOrderPost("neomaa", "/api/neomaa/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/neomaa/order",
      stage: "method",
      reason:
        'GET is read-only. Live Neomaa OrderSend requires POST { live: true, confirm: "NEOMAA-7745107", action: "open", volume_min: true }.',
      winePrefix: ".mt5-neomaa",
    },
    { status: 405 }
  );
}
