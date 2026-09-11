"use client";

import { useEffect, useRef, useState } from "react";
import type { DailyCall } from "@daily-co/daily-js";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { trpc } from "@/lib/trpc-client";
import { Button } from "./ui/button";

export function LiveConversation({ onActiveChange }: { onActiveChange: (active: boolean) => void }) {
  const [phase, setPhase] = useState<"idle" | "starting" | "connected" | "ending">("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [botPresent, setBotPresent] = useState(false);
  const call = useRef<DailyCall | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const busy = useRef(false);
  const cancelled = useRef(false);
  const attempt = useRef<string | null>(null);
  const start = trpc.voice.start.useMutation();
  const end = trpc.voice.end.useMutation();
  const state = trpc.voice.status.useQuery({ sessionId: sessionId ?? "" }, {
    enabled: Boolean(sessionId), refetchInterval: phase === "connected" ? 2000 : false,
    retry: false,
  });

  useEffect(() => {
    cancelled.current = false;
    return () => { cancelled.current = true; void call.current?.destroy(); };
  }, []);

  useEffect(() => onActiveChange(phase !== "idle"), [onActiveChange, phase]);

  useEffect(() => {
    if (state.data?.status === "failed" || state.data?.status === "ended") {
      void call.current?.leave();
    }
  }, [state.data?.status]);

  async function release() {
    const current = call.current;
    call.current = null;
    if (current) await current.destroy();
    if (audio.current) audio.current.srcObject = null;
    setBotPresent(false);
    setMuted(false);
  }

  async function disconnect() {
    if (busy.current) return;
    busy.current = true;
    setPhase("ending");
    try {
      await release();
      if (sessionId) await end.mutateAsync({ sessionId });
    } catch { setError("Audio stopped. Server cleanup could not be confirmed; the room expires automatically."); }
    finally { setSessionId(null); setPhase("idle"); busy.current = false; attempt.current = null; }
  }

  async function connect() {
    if (busy.current) return;
    busy.current = true;
    setPhase("starting"); setError("");
    let createdId: string | null = null;
    try {
      // Ask before creating a paid room; this click follows the visible disclosure below.
      const permission = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      permission.getTracks().forEach(track => track.stop());
      if (cancelled.current) throw new Error("Closed");
      attempt.current ??= crypto.randomUUID();
      const connection = await start.mutateAsync({ requestId: attempt.current });
      createdId = connection.session_id;
      if (cancelled.current) throw new Error("Closed");
      setSessionId(createdId);
      const Daily = (await import("@daily-co/daily-js")).default;
      const current = Daily.createCallObject({ videoSource: false });
      call.current = current;
      current.on("track-started", event => {
        if (event?.participant?.local || event?.track.kind !== "audio") return;
        setBotPresent(true);
        if (audio.current) {
          audio.current.srcObject = new MediaStream([event.track]);
          void audio.current.play().catch(() => setError("Press Play audio to hear the agent."));
        }
      });
      current.on("participant-left", () => setBotPresent(false));
      current.on("error", () => setError("The audio connection failed. End the call and try again."));
      current.on("left-meeting", () => setBotPresent(false));
      await current.join({ url: connection.room_url, token: connection.token, userName: "You" });
      if (cancelled.current) throw new Error("Closed");
      setPhase("connected");
    } catch (failure) {
      const denied = failure instanceof DOMException && failure.name === "NotAllowedError";
      setError(denied ? "Microphone permission was denied. Allow microphone access and try again." : "Could not connect. Check your microphone and provider configuration, then retry.");
      await release();
      if (createdId) {
        await end.mutateAsync({ sessionId: createdId }).catch(() => undefined);
        attempt.current = null;
      }
      setSessionId(null); setPhase("idle");
    } finally { busy.current = false; }
  }

  const stopped = state.data?.status === "failed" || state.data?.status === "ended";
  return <div className="live-conversation">
    <p>Live English conversation. Audio and text are processed by Daily, ElevenLabs and OpenRouter. This app does not save recordings; conversation context lasts for this call.</p>
    <p>We can clarify your situation here. Financial calculations and saved plans are not connected yet.</p>
    <div role="status" aria-live="polite">
      {phase === "idle" ? "Ready when you are." : phase === "starting" ? "Connecting your microphone and agent…" : phase === "ending" ? "Ending conversation…" : stopped ? "Conversation stopped." : botPresent ? "Connected — speak naturally, and interrupt whenever needed." : "Connected — waiting for the agent…"}
    </div>
    {(error || state.data?.error || state.error) && <p role="alert">{error || state.data?.error || "Connection status unavailable. End the call and try again."}</p>}
    <audio ref={audio} autoPlay controls aria-label="Agent audio" />
    <div className="flex flex-wrap gap-3">
      {phase === "idle" ? <Button onClick={connect}><Mic size={16} />Start live conversation</Button> : <>
        <Button variant="outline" disabled={phase !== "connected" || stopped} onClick={() => {
          call.current?.setLocalAudio(muted); setMuted(!muted);
        }}>{muted ? <MicOff size={16} /> : <Mic size={16} />}{muted ? "Unmute" : "Mute"}</Button>
        <Button variant="destructive" disabled={phase !== "connected"} onClick={disconnect}><PhoneOff size={16} />End conversation</Button>
      </>}
    </div>
  </div>;
}
