import { getMigrations } from "better-auth/db/migration";
import { getAuth } from "../src/lib/auth";
import { getPool } from "../src/lib/db";

async function migrate() {
  try {
    const { runMigrations } = await getMigrations(getAuth().options);
    await runMigrations();
    console.log("Authentication schema is ready.");
  } catch {
    console.error("Authentication migration failed. Check database connectivity and configuration.");
    process.exitCode = 1;
  } finally {
    await getPool().end();
  }
}
void migrate();
