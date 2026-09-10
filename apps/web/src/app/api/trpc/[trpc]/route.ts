import { fetchRequestHandler } from "@trpc/server/adapters/fetch";
import { appRouter } from "@/server/router";
import { createContext } from "@/server/trpc";

function handler(req: Request) {
  if (req.method !== "GET" && req.headers.get("origin") !== (process.env.APP_ORIGIN ?? "http://localhost:3000")) {
    return new Response("Forbidden", { status: 403 });
  }
  return fetchRequestHandler({ endpoint: "/api/trpc", req, router: appRouter, createContext: () => createContext(req.headers) });
}
export { handler as GET, handler as POST };
