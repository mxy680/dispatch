export type EarconType = "listening" | "thinking" | "approval" | "success" | "error";

let audioCtx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  audioCtx = audioCtx ?? new AudioContext();
  return audioCtx;
}

export function playEarcon(type: EarconType) {
  const ctx = getCtx();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  const now = ctx.currentTime;
  const profile: Record<EarconType, [number, number]> = {
    listening: [880, 0.06],
    thinking: [660, 0.08],
    approval: [520, 0.12],
    success: [980, 0.08],
    error: [220, 0.14],
  };
  const [freq, dur] = profile[type];
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.08, now + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  osc.start(now);
  osc.stop(now + dur + 0.01);
}
