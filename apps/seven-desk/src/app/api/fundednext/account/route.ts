import { fundednextAccountSnapshot, probeFundedNextLive } from "@/lib/fundednext/probe";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(fundednextAccountSnapshot(probeFundedNextLive()));
}
