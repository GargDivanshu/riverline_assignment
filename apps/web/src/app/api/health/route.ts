import { getPool } from "@/lib/db";

export const dynamic = "force-dynamic";
export async function GET() {
  try {
    await getPool().query("SELECT 1");
    return Response.json({ status: "ok" });
  } catch {
    return Response.json({ status: "unavailable" }, { status: 503 });
  }
}
