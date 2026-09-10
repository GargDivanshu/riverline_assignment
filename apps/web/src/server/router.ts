import { TRPCError } from "@trpc/server";
import { agentClient } from "@/lib/api/client";
import { protectedProcedure, router } from "./trpc";

export const appRouter = router({
  workspace: router({
    get: protectedProcedure.query(async ({ ctx }) => {
      try {
        const { data, error } = await agentClient(ctx.session.user.id).GET("/v1/workspace");
        if (error || !data) throw new Error("Agent unavailable");
        return data;
      } catch {
        throw new TRPCError({ code: "SERVICE_UNAVAILABLE", message: "Your workspace couldn't be loaded. Please try again." });
      }
    }),
  }),
});
export type AppRouter = typeof appRouter;
