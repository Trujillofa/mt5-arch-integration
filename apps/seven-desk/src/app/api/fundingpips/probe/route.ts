import { probeFundingPipsLive } from "@/lib/fundingpips/probe";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(probeFundingPipsLive());
}
