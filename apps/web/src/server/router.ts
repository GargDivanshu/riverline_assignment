import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { agentClient } from "@/lib/api/client";
import { protectedProcedure, router } from "./trpc";

export const appRouter = router({
  voice: router({
    start: protectedProcedure.input(z.object({ requestId: z.uuid() })).mutation(async ({ ctx, input }) => {
      try {
        const result = await agentClient(ctx.session.user.id, 40_000).POST("/v1/voice/start", {
          body: { request_id: input.requestId },
        });
        if (!result.data) throw new Error();
        return result.data;
      } catch {
        throw new TRPCError({ code: "SERVICE_UNAVAILABLE", message: "Could not start voice. Check provider configuration or an existing call, then retry." });
      }
    }),
    status: protectedProcedure.input(z.object({ sessionId: z.uuid() })).query(async ({ ctx, input }) => {
      const result = await agentClient(ctx.session.user.id).GET("/v1/voice/{session_id}", {
        params: { path: { session_id: input.sessionId } },
      });
      if (!result.data) throw new TRPCError({ code: "NOT_FOUND", message: "Voice session is unavailable." });
      return result.data;
    }),
    end: protectedProcedure.input(z.object({ sessionId: z.uuid() })).mutation(async ({ ctx, input }) => {
      const result = await agentClient(ctx.session.user.id, 30_000).POST("/v1/voice/{session_id}/end", {
        params: { path: { session_id: input.sessionId } },
      });
      if (!result.data) throw new TRPCError({ code: "SERVICE_UNAVAILABLE", message: "Call cleanup could not be confirmed. The room will expire automatically." });
      return result.data;
    }),
  }),
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
