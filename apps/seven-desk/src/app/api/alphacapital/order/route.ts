import { defaultLotsForFirm } from "@/lib/firms";
import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleLiveOrderPost("alphacapital", "/api/alphacapital/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/alphacapital/order",
      stage: "method",
      reason:
        `GET is read-only. Live Alpha Capital OrderSend requires POST { live: true, confirm: "ACG-2765247", action: "open" }. Default ${defaultLotsForFirm("alphacapital")} lots (market / limit / stop). volume_min: true is the 0.01 prove.`,
      winePrefix: ".mt5-alphacapital",
    },
    { status: 405 }
  );
}
