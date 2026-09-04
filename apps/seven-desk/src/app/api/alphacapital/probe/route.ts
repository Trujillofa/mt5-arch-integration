import { probeAlphaCapitalLive } from "@/lib/alphacapital/probe";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(probeAlphaCapitalLive());
}
