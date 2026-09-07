import { probeFundingPipsLive } from "@/lib/fundingpips/probe";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const poll = new URL(req.url).searchParams.get("poll") === "1";
  return Response.json(probeFundingPipsLive({ poll }));
}
