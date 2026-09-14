import { defaultLotsHelp } from "@/lib/firms";
import { handleWsfLiveOrderPost } from "@/lib/wsf/live-order";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleWsfLiveOrderPost("/api/wsf/order");

export async function GET() {
  return Response.json(
    {
      ok: false,
      source: "seven-desk",
      endpoint: "/api/wsf/order",
      stage: "method",
      reason:
        `GET is read-only. Live WSF OrderSend requires POST { live: true, confirm: "WSF-149736", action: "open" }. Scratch stays volume_min. ${defaultLotsHelp("wsf")}`,
      winePrefix: ".mt5-wsf",
    },
    { status: 405 }
  );
}
