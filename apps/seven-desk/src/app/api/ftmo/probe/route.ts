import { probeFtmoLive } from "@/lib/ftmo/probe";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(probeFtmoLive());
}
