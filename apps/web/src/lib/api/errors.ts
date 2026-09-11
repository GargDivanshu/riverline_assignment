import { TRPCError } from "@trpc/server";

type AgentFailure = {
  error?: {
    code?: unknown;
    message?: unknown;
    retryable?: unknown;
  };
  detail?: unknown;
};

type AgentResult = {
  error?: unknown;
  response?: Response;
};

function failureBody(value: unknown): AgentFailure["error"] | undefined {
  if (!value || typeof value !== "object") return undefined;
  const candidate = value as AgentFailure;
  return candidate.error && typeof candidate.error === "object" ? candidate.error : undefined;
}

function trpcCode(status?: number): TRPCError["code"] {
  if (status === 400 || status === 422) return "BAD_REQUEST";
  if (status === 401) return "UNAUTHORIZED";
  if (status === 404) return "NOT_FOUND";
  if (status === 409) return "CONFLICT";
  if (status === 429) return "TOO_MANY_REQUESTS";
  return "SERVICE_UNAVAILABLE";
}

/** Translate only our server's structured, safe error contract into tRPC. */
export function agentError(result: AgentResult, fallback: string): TRPCError {
  const error = failureBody(result.error);
  const message = typeof error?.message === "string" ? error.message : fallback;
  return new TRPCError({ code: trpcCode(result.response?.status), message });
}

export function networkError(fallback: string): TRPCError {
  return new TRPCError({ code: "SERVICE_UNAVAILABLE", message: fallback });
}
