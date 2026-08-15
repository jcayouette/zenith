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
};

export function formatExposure(us: number) {
  if (!us) return "—";
  if (us >= 1_000_000) return `${(us / 1_000_000).toFixed(2)} s`;
  if (us >= 1000) return `${Math.round(us / 1000)} ms`;
  return `${us} µs`;
}
