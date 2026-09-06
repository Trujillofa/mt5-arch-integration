import { handleWsfLiveOrderPost } from "@/lib/wsf/live-order";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export const POST = handleWsfLiveOrderPost("/api/wsf/order/close", "close");
