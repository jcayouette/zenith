import SkyCard, { Metric, Row } from "@/components/SkyCard";

export const AC_COLOR = "#e2e8f0";
export const AC_INBOUND = "#4ade80";
export const AC_YELLOW = "#facc15";
export const AC_ORANGE = "#fb923c";
export const AC_RED = "#f87171";

/** Elevation traffic light: 0–20 yellow, 20–30 orange, 30+ red from any azimuth. */
export function acBand(alt?: number): "yellow" | "orange" | "red" | null {
  if (alt == null || !Number.isFinite(alt)) return null;
  if (alt >= 30) return "red";
  if (alt >= 20) return "orange";
  if (alt >= 0) return "yellow";
  return null;
}

export function acColor(alt?: number, inbound?: boolean): string {
  const band = acBand(alt);
  if (band === "red") return AC_RED;
  if (band === "orange") return AC_ORANGE;
  if (band === "yellow") return AC_YELLOW;
  return inbound ? AC_INBOUND : AC_COLOR;
}

export function acPathStroke(color: string, inbound: boolean): string {
  const alpha = inbound ? 0.5 : 0.38;
  if (color.startsWith("#") && (color.length === 7 || color.length === 4)) {
    const hex = color.length === 4 ? `#${color[1]}${color[1]}${color[2]}${color[2]}${color[3]}${color[3]}` : color;
    const n = Number.parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return color;
}

export type AcLive = {
  id?: string;
  name?: string;
  icao24?: string;
  country?: string;
  alt?: number;
  az?: number;
  alt_m?: number;
  range_km?: number;
  gs_kmh?: number;
  heading?: number;
  vrate_ms?: number;
  squawk?: string;
  category?: string;
  cpa_km?: number;
  tca_s?: number;
  inbound?: boolean;
  from_x?: number;
  from_y?: number;
  path?: Array<{ x: number; y: number }>;
};

export type AcMeta = {
  icao24?: string;
  typecode?: string | null;
  model?: string | null;
  manufacturer?: string | null;
  registration?: string | null;
  operator?: string | null;
  label?: string | null;
  error?: string;
};

type Props = {
  ac: AcLive;
  meta?: AcMeta | null;
  loading?: boolean;
  onClose: () => void;
};

export default function AcInspector({ ac, meta, loading, onClose }: Props) {
  const inbound = Boolean(ac.inbound);
  const band = acBand(ac.alt);
  const accent = acColor(ac.alt, inbound);
  const typeLabel = meta?.label || [meta?.manufacturer, meta?.model].filter(Boolean).join(" ");
  const kicker =
    band === "red"
      ? "Danger overhead"
      : meta?.typecode || (band === "orange" ? "High" : band === "yellow" ? "Horizon" : inbound ? "Inbound" : ac.category || "Aircraft");
  return (
    <SkyCard
      accent={accent}
      kicker={kicker}
      title={ac.name || ac.icao24 || "Aircraft"}
      onClose={onClose}
    >
      {typeLabel ? (
        <p className="border-t border-white/8 px-3.5 py-2.5 text-[11px] leading-snug text-white/80">{typeLabel}</p>
      ) : loading ? (
        <p className="border-t border-white/8 px-3.5 py-2.5 text-[11px] text-white/35">Looking up type…</p>
      ) : meta?.error ? (
        <p className="border-t border-white/8 px-3.5 py-2.5 text-[11px] leading-snug text-white/65">
          {inbound
            ? "Track will pass within 50 km. Type not in the public ICAO24 database."
            : "Already inside 50 km. Type not in the public ICAO24 database."}
        </p>
      ) : (
        <p className="border-t border-white/8 px-3.5 py-2.5 text-[11px] leading-snug text-white/65">
          {inbound
            ? "Track will pass within 50 km. Green horizon dot is where it is coming from."
            : "Already inside 50 km of the camera."}
        </p>
      )}
      <dl className="grid grid-cols-3 gap-px border-t border-white/8 bg-white/6 text-center">
        <Metric label="Alt" value={ac.alt != null ? `${ac.alt.toFixed(1)}°` : "—"} />
        <Metric label="Az" value={ac.az != null ? `${ac.az.toFixed(1)}°` : "—"} />
        <Metric label="CPA" value={ac.cpa_km != null ? `${ac.cpa_km.toFixed(0)} km` : "—"} />
      </dl>
      <dl className="space-y-1.5 px-3.5 py-3 text-[11px]">
        <Row label="Callsign" value={ac.name || "—"} />
        {meta?.registration ? <Row label="Tail" value={meta.registration} /> : null}
        {meta?.operator ? <Row label="Operator" value={meta.operator} /> : null}
        {meta?.typecode ? <Row label="ICAO" value={meta.typecode} /> : null}
        <Row label="ICAO24" value={ac.icao24 || ac.id || "—"} />
        {ac.country ? <Row label="Country" value={ac.country} /> : null}
        {ac.alt_m != null ? <Row label="Height" value={`${Math.round(ac.alt_m)} m`} /> : null}
        {ac.range_km != null ? <Row label="Range" value={`${fmtKm(ac.range_km)} km`} /> : null}
        {ac.gs_kmh != null ? <Row label="Speed" value={`${Math.round(ac.gs_kmh)} km/h`} /> : null}
        {ac.heading != null ? <Row label="Track" value={`${Math.round(ac.heading)}°`} /> : null}
        {inbound && ac.tca_s != null && ac.tca_s > 0 ? <Row label="Overhead" value={fmtEta(ac.tca_s)} /> : null}
        {ac.vrate_ms ? <Row label="Climb" value={`${ac.vrate_ms > 0 ? "+" : ""}${ac.vrate_ms.toFixed(1)} m/s`} /> : null}
        {ac.squawk ? <Row label="Squawk" value={ac.squawk} /> : null}
      </dl>
    </SkyCard>
  );
}

function fmtKm(km: number) {
  return km >= 1000 ? km.toFixed(0) : km.toFixed(1);
}

function fmtEta(sec: number) {
  if (sec < 90) return `${Math.round(sec)} s`;
  const m = Math.round(sec / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} m`;
}
