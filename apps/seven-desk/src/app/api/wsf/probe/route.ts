import { probeWsfLive } from "@/lib/wsf/live-client";

export const dynamic = "force-dynamic";

export async function GET() {
  const report = await probeWsfLive();
  return Response.json(report);
}
