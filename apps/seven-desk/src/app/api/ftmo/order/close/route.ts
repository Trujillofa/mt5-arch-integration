import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 180;

export const POST = handleLiveOrderPost("ftmo", "/api/ftmo/order/close", "close");
