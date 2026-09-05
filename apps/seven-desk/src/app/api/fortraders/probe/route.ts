import { probeFortradersLive } from "@/lib/fortraders/probe";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(probeFortradersLive());
}
