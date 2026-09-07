import { probeNeomaaLive } from "@/lib/neomaa/probe";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const poll = new URL(req.url).searchParams.get("poll") === "1";
  return Response.json(probeNeomaaLive({ poll }));
}
