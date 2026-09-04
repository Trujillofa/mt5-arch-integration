import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 180;

export const POST = handleLiveOrderPost("fundednext", "/api/fundednext/order/close", "close");
