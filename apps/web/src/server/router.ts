import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { agentClient } from "@/lib/api/client";
import { agentError, networkError } from "@/lib/api/errors";
import { protectedProcedure, router } from "./trpc";

export const appRouter = router({
  voice: router({
    start: protectedProcedure.input(z.object({ requestId: z.uuid() })).mutation(async ({ ctx, input }) => {
      try {
        const result = await agentClient(ctx.session.user.id, 40_000).POST("/v1/voice/start", {
          body: { request_id: input.requestId },
        });
        if (!result.data) throw agentError(result, "Could not start voice. Try again shortly.");
        return result.data;
      } catch (error) {
        if (error instanceof TRPCError) throw error;
        throw networkError("Could not reach the voice service. Try again shortly.");
      }
    }),
    status: protectedProcedure.input(z.object({ sessionId: z.uuid() })).query(async ({ ctx, input }) => {
      try {
        const result = await agentClient(ctx.session.user.id).GET("/v1/voice/{session_id}", {
          params: { path: { session_id: input.sessionId } },
        });
        if (!result.data) throw agentError(result, "Voice session is unavailable.");
        return result.data;
      } catch (error) {
        if (error instanceof TRPCError) throw error;
        throw networkError("Could not check the voice session. The room will expire automatically.");
      }
    }),
    end: protectedProcedure.input(z.object({ sessionId: z.uuid() })).mutation(async ({ ctx, input }) => {
      try {
        const result = await agentClient(ctx.session.user.id, 30_000).POST("/v1/voice/{session_id}/end", {
          params: { path: { session_id: input.sessionId } },
        });
        if (!result.data) throw agentError(result, "Call cleanup could not be confirmed. The room will expire automatically.");
        return result.data;
      } catch (error) {
        if (error instanceof TRPCError) throw error;
        throw networkError("Call cleanup could not be confirmed. The room will expire automatically.");
      }
    }),
  }),
  workspace: router({
    get: protectedProcedure.query(async ({ ctx }) => {
      try {
        const { data, error } = await agentClient(ctx.session.user.id).GET("/v1/workspace");
        if (error || !data) throw agentError({ error }, "Your workspace couldn't be loaded. Please try again.");
        return data;
      } catch (error) {
        if (error instanceof TRPCError) throw error;
        throw networkError("Your workspace couldn't be loaded. Please try again.");
      }
    }),
  }),
});
export type AppRouter = typeof appRouter;
