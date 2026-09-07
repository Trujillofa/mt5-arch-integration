import { probeWsfLive } from "@/lib/wsf/live-client";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const poll = new URL(req.url).searchParams.get("poll") === "1";
  const report = await probeWsfLive({ poll });
  return Response.json(report);
}
