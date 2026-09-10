import { initTRPC, TRPCError } from "@trpc/server";
import { getAuth } from "@/lib/auth";

export async function createContext(headers: Headers) {
  const session = await getAuth().api.getSession({ headers });
  return { session };
}

export type Context = Awaited<ReturnType<typeof createContext>>;
const t = initTRPC.context<Context>().create();
export const router = t.router;
export const protectedProcedure = t.procedure.use(({ ctx, next }) => {
  if (!ctx.session) throw new TRPCError({ code: "UNAUTHORIZED" });
  return next({ ctx: { session: ctx.session } });
});
