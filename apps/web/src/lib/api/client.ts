import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { requiredEnv } from "../env";

export function agentClient(userId: string) {
  return createClient<paths>({
    baseUrl: process.env.AGENT_API_URL ?? "http://localhost:8000",
    headers: {
      Authorization: `Bearer ${requiredEnv("INTERNAL_API_SECRET")}`,
      "X-User-Id": userId,
    },
    fetch: (request) => fetch(request, { cache: "no-store", signal: AbortSignal.timeout(5_000) }),
  });
}
