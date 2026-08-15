import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type Telemetry = {
  mode: string;
  sun_alt: number;
  exposure_us: number;
  gain: number;
  adu: number;
  backend: string;
  sensor: string;
  ts: string;
  error: string | null;
  capturing: boolean;
  session: string;
  stars: number;
  saved: boolean;
  focus: boolean;
  camera?: boolean;
};

export function formatExposure(us: number) {
  return formatShutter(us);
}

export function formatShutter(us: number) {
  if (!us) return "—";
  if (us >= 1_000_000) {
    const s = us / 1_000_000;
    return `${s < 10 ? s.toFixed(2) : s.toFixed(1)} s`;
  }
  if (us >= 1000) {
    const ms = us / 1000;
    if (ms >= 100) return `${Math.round(ms)} ms`;
    if (ms >= 10) return `${ms.toFixed(1)} ms`;
    return `${ms.toFixed(2)} ms`;
  }
  return `${Math.round(us)} µs`;
}
