import { neomaaAccountSnapshot, probeNeomaaLive } from "@/lib/neomaa/probe";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(neomaaAccountSnapshot(probeNeomaaLive()));
}
