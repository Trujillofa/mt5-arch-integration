import { handleLiveOrderPost } from "@/lib/live-order/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleLiveOrderPost("fortraders", "/api/fortraders/order/close", "close");
