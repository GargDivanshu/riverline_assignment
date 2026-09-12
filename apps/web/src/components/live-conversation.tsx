"use client";

import { useEffect, useRef, useState } from "react";
import type { DailyCall } from "@daily-co/daily-js";
import { AudioLines, LoaderCircle, Mic, MicOff, PhoneOff, Sparkles, Volume2 } from "lucide-react";
import { trpc } from "@/lib/trpc-client";
import { Button } from "./ui/button";

export function LiveConversation({ onActiveChange, mode = "returning" }: { onActiveChange: (active: boolean) => void; mode?: "new" | "returning" }) {
  const [phase, setPhase] = useState<"idle" | "starting" | "connected" | "ending">("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const call = useRef<DailyCall | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const busy = useRef(false);
  const cancelled = useRef(false);
  const attempt = useRef<string | null>(null);
  const agentSpoke = useRef(false);
  const joinTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const start = trpc.voice.start.useMutation();
  const end = trpc.voice.end.useMutation();
  const state = trpc.voice.status.useQuery({ sessionId: sessionId ?? "" }, {
    enabled: Boolean(sessionId), refetchInterval: phase === "connected" ? 2000 : false,
    retry: false,
  });

  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
      if (joinTimeout.current) clearTimeout(joinTimeout.current);
      void call.current?.destroy();
    };
  }, []);

  useEffect(() => onActiveChange(phase !== "idle"), [onActiveChange, phase]);

  useEffect(() => {
    if (state.data?.activity !== "speaking") return;
    agentSpoke.current = true;
    if (joinTimeout.current) clearTimeout(joinTimeout.current);
  }, [state.data?.activity]);

  useEffect(() => {
    if (state.data?.status === "failed" || state.data?.status === "ended") {
      void release().finally(() => {
        if (state.data?.error) setError(state.data.error);
        setSessionId(null);
        setPhase("idle");
        attempt.current = null;
      });
    }
  // release is a function declaration so it is stable for this lifecycle effect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.data?.status]);

  async function release() {
    const current = call.current;
    call.current = null;
    if (current) await current.destroy();
    if (joinTimeout.current) clearTimeout(joinTimeout.current);
    joinTimeout.current = null;
    agentSpoke.current = false;
    if (audio.current) audio.current.srcObject = null;
    setAudioBlocked(false);
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
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("microphone_unavailable");
      const permission = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      permission.getTracks().forEach(track => track.stop());
      if (cancelled.current) throw new Error("Closed");
      attempt.current ??= crypto.randomUUID();
      const connection = await start.mutateAsync({ requestId: attempt.current, conversationMode: mode });
      createdId = connection.session_id;
      if (cancelled.current) throw new Error("Closed");
      setSessionId(createdId);
      const Daily = (await import("@daily-co/daily-js")).default;
      const current = Daily.createCallObject({ videoSource: false });
      call.current = current;
      current.on("track-started", event => {
        if (event?.participant?.local || event?.track.kind !== "audio") return;
        if (audio.current) {
          audio.current.srcObject = new MediaStream([event.track]);
          void audio.current.play().catch(() => setAudioBlocked(true));
        }
      });
      current.on("error", () => {
        setError("The audio connection failed. Ending the call safely.");
        void disconnect();
      });
      await current.join({ url: connection.room_url, token: connection.token, userName: "You" });
      if (cancelled.current) throw new Error("Closed");
      setPhase("connected");
      joinTimeout.current = setTimeout(() => {
        if (agentSpoke.current) return;
        setError("Riverline could not begin this call. Ending it safely — please try again.");
        void disconnect();
      }, 15_000);
    } catch (failure) {
      const denied = failure instanceof DOMException && failure.name === "NotAllowedError";
      const unavailable = failure instanceof Error && failure.message === "microphone_unavailable";
      const providerMessage = safeMutationMessage(failure);
      setError(denied ? "Microphone permission was denied. Allow microphone access and try again." : unavailable ? "Microphone access is unavailable in this browser." : providerMessage ?? "Could not connect. Check your microphone and provider configuration, then retry.");
      await release();
      if (createdId) {
        await end.mutateAsync({ sessionId: createdId }).catch(() => undefined);
        attempt.current = null;
      }
      setSessionId(null); setPhase("idle");
    } finally { busy.current = false; }
  }

  const stopped = state.data?.status === "failed" || state.data?.status === "ended";
  const activity = state.data?.activity;
  const status = phase === "idle" ? "Ready when you are" : phase === "starting" ? "Setting up a private call" : phase === "ending" ? "Ending your conversation" : activity === "speaking" ? "Riverline is speaking" : activity === "listening" ? "Your turn — Riverline is listening" : "Riverline is getting ready";
  return <div className="live-conversation">
    <div className={`voice-stage phase-${phase} ${activity === "speaking" ? "is-speaking" : ""}`}>
      <div className="voice-pulse" aria-hidden="true"><div><Sparkles size={24} /></div></div>
      <div className="voice-stage-copy">
        <span className="voice-status"><span className="voice-status-icon">{phase === "starting" || phase === "ending" ? <LoaderCircle size={15} className="animate-spin" /> : activity === "speaking" ? <Volume2 size={15} /> : <AudioLines size={15} />}</span>{status}</span>
        <p>{phase === "connected" && activity !== "speaking" && activity !== "listening" ? "This should take only a few seconds." : activity === "speaking" ? "You can interrupt whenever you need." : activity === "listening" ? "Speak naturally; pauses and corrections are okay." : "Your audio stays live only for this call."}</p>
      </div>
    </div>
    {(error || state.data?.error || state.error) && <p className="voice-error" role="alert">{error || state.data?.error || "Connection status unavailable. End the call and try again."}{state.data?.error_code && <small> Reference: {state.data.error_code}</small>}</p>}
    <audio ref={audio} autoPlay aria-label="Agent audio" />
    <div className="flex flex-wrap gap-3">
      {phase === "idle" ? <Button onClick={connect}><Mic size={16} />Start live conversation</Button> : <>
        <Button variant="outline" disabled={phase !== "connected" || stopped} onClick={() => {
          call.current?.setLocalAudio(muted); setMuted(!muted);
        }}>{muted ? <MicOff size={16} /> : <Mic size={16} />}{muted ? "Unmute" : "Mute"}</Button>
        <Button variant="destructive" disabled={phase !== "connected"} onClick={disconnect}><PhoneOff size={16} />End conversation</Button>
      </>}
      {audioBlocked && <Button variant="outline" onClick={() => void audio.current?.play().then(() => setAudioBlocked(false)).catch(() => undefined)}><Volume2 size={16} />Enable agent audio</Button>}
    </div>
    <p className="voice-disclosure">English voice is processed by Daily, ElevenLabs and OpenRouter. Recordings are not saved; context ends with this call.</p>
  </div>;
}

function safeMutationMessage(failure: unknown): string | undefined {
  if (!failure || typeof failure !== "object") return undefined;
  const candidate = failure as { data?: unknown; message?: unknown };
  if (!candidate.data || typeof candidate.data !== "object" || typeof candidate.message !== "string") return undefined;
  return candidate.message.length <= 180 ? candidate.message : undefined;
}
