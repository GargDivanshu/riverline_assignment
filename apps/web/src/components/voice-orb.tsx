"use client";
import { ThinkingOrb } from "thinking-orbs";
import { useReducedMotion } from "motion/react";
import type { OrbState } from "thinking-orbs";

export function VoiceOrb({ speaking = false, listening = false }: { speaking?: boolean; listening?: boolean }) {
  const reducedMotion = useReducedMotion();
  const state: OrbState = speaking ? "composing" : listening ? "listening" : "breathing";
  return <div className={`voice-orb ${speaking ? "is-speaking" : ""} ${listening ? "is-listening" : ""}`} aria-hidden="true">
    <div className="orb-glow" />
    <div className="orb-ring ring-one" /><div className="orb-ring ring-two" />
    <ThinkingOrb state={state} theme="light" size={64} speed={speaking ? 0.9 : 0.55} paused={Boolean(reducedMotion)} />
  </div>;
}
