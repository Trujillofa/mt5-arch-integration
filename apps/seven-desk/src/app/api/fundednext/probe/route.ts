import { probeFundedNextLive } from "@/lib/fundednext/probe";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const poll = new URL(req.url).searchParams.get("poll") === "1";
  return Response.json(probeFundedNextLive({ poll }));
}
