"use client";
import { ThinkingOrb } from "thinking-orbs";
import { useReducedMotion } from "motion/react";

export function VoiceOrb() {
  const reducedMotion = useReducedMotion();
  return <div className="voice-orb" aria-hidden="true"><div className="orb-ring ring-one" /><div className="orb-ring ring-two" /><ThinkingOrb state="breathing" theme="light" size={64} speed={0.55} paused={Boolean(reducedMotion)} /></div>;
}
