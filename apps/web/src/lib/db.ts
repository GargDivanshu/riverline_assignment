import { Pool } from "pg";
import { requiredEnv } from "./env";

const globalDb = globalThis as unknown as { riverlinePool?: Pool };
export function getPool() {
  return globalDb.riverlinePool ??= new Pool({
    connectionString: requiredEnv("DATABASE_URL"),
    max: 5,
    connectionTimeoutMillis: 5_000,
    idleTimeoutMillis: 30_000,
  });
}
