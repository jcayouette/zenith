import { useEffect, useRef, useState } from "react";

export type SatPt = {
  x: number;
  y: number;
  alt?: number;
  az?: number;
  name?: string;
  x2?: number;
  y2?: number;
  norad?: string;
  kind?: string;
  range_km?: number;
};

export const SAT_KIND: Record<string, { label: string; color: string }> = {
  station: { label: "Station", color: "#ffe566" },
  starlink: { label: "Starlink", color: "#7dd3fc" },
  oneweb: { label: "OneWeb", color: "#67e8f9" },
  kuiper: { label: "Kuiper", color: "#f0abfc" },
  military: { label: "Military", color: "#fb7185" },
  gnss: { label: "GNSS", color: "#86efac" },
  weather: { label: "Weather", color: "#38bdf8" },
  science: { label: "Science", color: "#c4b5fd" },
  geo: { label: "GEO", color: "#fde68a" },
  planet: { label: "Planet", color: "#fdba74" },
  comms: { label: "Comms", color: "#2dd4bf" },
  other: { label: "Other", color: "#fbbf24" },
};

export function satKindOf(sat: { kind?: string }) {
  return sat.kind && SAT_KIND[sat.kind] ? sat.kind : "other";
}

export const SAT_EMOJI = "🛰️";

function emojiSize(mega: boolean, station: boolean, scale: number) {
  return (mega ? 9 : station ? 16 : 13) * scale;
}

type Track = {
  id: string;
  name: string;
  norad: string;
  kind: string;
  x0: number;
  y0: number;
  vx: number;
  vy: number;
  t0: number;
  alt: number;
  az: number;
  range_km?: number;
};

type Props = {
  samples: SatPt[];
  dt: number;
  fit: number;
  iconScale: number;
  kinds: string[] | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  kindCounts: Record<string, number>;
};

const STALE_MS = 1600;

export default function SatLayer({
  samples,
  dt,
  fit,
  iconScale,
  kinds,
  selectedId,
  onSelect,
  kindCounts,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tracksRef = useRef(new Map<string, Track>());
  const dtRef = useRef(dt);
  const fitRef = useRef(fit);
  const scaleRef = useRef(iconScale);
  const kindsRef = useRef(kinds);
  const selectedRef = useRef(selectedId);
  const onSelectRef = useRef(onSelect);
  const [picked, setPicked] = useState<Track | null>(null);
  const [panel, setPanel] = useState<{ x: number; y: number } | null>(null);

  dtRef.current = dt;
  fitRef.current = fit;
  scaleRef.current = iconScale;
  kindsRef.current = kinds;
  selectedRef.current = selectedId;
  onSelectRef.current = onSelect;

  useEffect(() => {
    tracksRef.current = ingest(samples, dt, performance.now(), tracksRef.current);
  }, [samples, dt]);

  useEffect(() => {
    if (!selectedId) {
      setPicked(null);
      setPanel(null);
      return;
    }
    const track = tracksRef.current.get(selectedId);
    if (track) {
      setPicked({ ...track });
      setPanel((pos) => pos ?? { x: 12, y: 12 });
    }
  }, [selectedId, samples]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      onSelectRef.current(null);
      setPicked(null);
      setPanel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const wrap = canvas.parentElement;
    if (!wrap) return;
    let raf = 0;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);

    const draw = (now: number) => {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      ctx.clearRect(0, 0, w, h);
      const allow = kindsRef.current ? new Set(kindsRef.current) : null;
      const fitNow = fitRef.current;
      const icon = scaleRef.current;
      const selected = selectedRef.current;
      const maxAge = Math.max(dtRef.current * 1.6, 1.2);
      for (const track of tracksRef.current.values()) {
        if (allow && !allow.has(track.kind) && track.id !== selected) continue;
        const age = Math.min((now - track.t0) / 1000, maxAge);
        const x = track.x0 + track.vx * age;
        const y = track.y0 + track.vy * age;
        const [px, py] = overlayToPixel(x, y, fitNow, w, h);
        if (px < -8 || py < -8 || px > w + 8 || py > h + 8) continue;
        const mega = track.kind === "starlink" || track.kind === "oneweb";
        const color = SAT_KIND[track.kind]?.color ?? SAT_KIND.other.color;
        const size = emojiSize(mega, track.kind === "station", icon);
        const sprite = tintedSatSprite(color, size);
        if (track.id === selected) {
          ctx.strokeStyle = "rgba(255,255,255,0.85)";
          ctx.lineWidth = 1.4;
          ctx.beginPath();
          ctx.arc(px, py, size * 0.55, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.drawImage(sprite, px - sprite.width / 2, py - sprite.height / 2);
        if (track.id === selected || track.kind === "station") {
          ctx.textAlign = "left";
          ctx.textBaseline = "alphabetic";
          ctx.font = track.id === selected ? "700 12px ui-sans-serif, system-ui" : "600 11px ui-sans-serif, system-ui";
          ctx.fillStyle = "#041018";
          ctx.fillText(track.name, px + size * 0.45, py - 6);
          ctx.fillStyle = color;
          ctx.fillText(track.name, px + size * 0.45 - 0.5, py - 6.5);
        }
      }
      raf = window.requestAnimationFrame(draw);
    };
    raf = window.requestAnimationFrame(draw);
    return () => {
      window.cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  function hitTest(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    const [ox, oy] = pixelToOverlay(px, py, fitRef.current, rect.width, rect.height);
    const allow = kindsRef.current ? new Set(kindsRef.current) : null;
    const now = performance.now();
    const maxAge = Math.max(dtRef.current * 1.6, 1.2);
    let best: Track | null = null;
    let bestD = 18 / Math.min(rect.width, rect.height);
    for (const track of tracksRef.current.values()) {
      if (allow && !allow.has(track.kind)) continue;
      const age = Math.min((now - track.t0) / 1000, maxAge);
      const x = track.x0 + track.vx * age;
      const y = track.y0 + track.vy * age;
      const d = Math.hypot(x - ox, y - oy);
      const pad = track.kind === "station" ? 1.8 : 1.35;
      if (d < bestD * pad) {
        bestD = d;
        best = { ...track, x0: x, y0: y };
      }
    }
    if (!best) {
      onSelectRef.current(null);
      setPicked(null);
      setPanel(null);
      return;
    }
    onSelectRef.current(best.id);
    setPicked(best);
    setPanel({
      x: Math.min(px + 12, rect.width - 240),
      y: Math.min(py + 12, rect.height - 220),
    });
  }

  return (
    <>
      <canvas
        ref={canvasRef}
        className="absolute inset-0 h-full w-full cursor-pointer"
        onClick={(e) => hitTest(e.clientX, e.clientY)}
      />
      {picked && panel ? (
        <aside
          className="absolute z-10 w-56 rounded-xl border border-white/12 bg-slate-950/92 p-3 shadow-xl backdrop-blur-sm"
          style={{ left: panel.x, top: panel.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-semibold leading-tight" style={{ color: SAT_KIND[picked.kind]?.color }}>
              {picked.name}
            </p>
            <button
              type="button"
              className="rounded px-1 text-xs text-white/45 hover:text-white"
              onClick={() => {
                onSelect(null);
                setPicked(null);
                setPanel(null);
              }}
              aria-label="Close"
            >
              ×
            </button>
          </div>
          <dl className="mt-2 space-y-1 text-[11px] text-white/70">
            <Row label="Type" value={SAT_KIND[picked.kind]?.label ?? picked.kind} />
            <Row label="NORAD" value={picked.norad || "—"} />
            <Row label="Alt" value={`${picked.alt.toFixed(1)}°`} />
            <Row label="Az" value={`${picked.az.toFixed(1)}°`} />
            {picked.range_km != null ? <Row label="Range" value={`${fmtKm(picked.range_km)} km`} /> : null}
          </dl>
          <p className="mt-3 text-[10px] uppercase tracking-[0.18em] text-white/35">Visible now</p>
          <ul className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-white/55">
            {Object.entries(SAT_KIND).map(([id, meta]) => (
              <li key={id} className="flex justify-between gap-2">
                <span>{meta.label}</span>
                <span className="tabular-nums text-white/75">{kindCounts[id] ?? 0}</span>
              </li>
            ))}
          </ul>
        </aside>
      ) : null}
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-white/40">{label}</dt>
      <dd className="tabular-nums text-white/85">{value}</dd>
    </div>
  );
}

function ingest(samples: SatPt[], dt: number, now: number, prev: Map<string, Track>): Map<string, Track> {
  const next = new Map<string, Track>();
  const look = Math.max(dt, 0.4);
  const catchup = Math.max(0.35, look * 0.85);
  for (const s of samples) {
    const id = s.norad || s.name || "";
    if (!id) continue;
    const kind = satKindOf(s);
    const vx = s.x2 != null ? (s.x2 - s.x) / look : 0;
    const vy = s.y2 != null ? (s.y2 - s.y) / look : 0;
    const old = prev.get(id);
    let x0 = s.x;
    let y0 = s.y;
    let ovx = vx;
    let ovy = vy;
    if (old) {
      const age = (now - old.t0) / 1000;
      const cx = old.x0 + old.vx * age;
      const cy = old.y0 + old.vy * age;
      const tx = s.x + vx * catchup;
      const ty = s.y + vy * catchup;
      x0 = cx;
      y0 = cy;
      ovx = (tx - cx) / catchup;
      ovy = (ty - cy) / catchup;
    }
    next.set(id, {
      id,
      name: s.name || id,
      norad: s.norad || "",
      kind,
      x0,
      y0,
      vx: ovx,
      vy: ovy,
      t0: now,
      alt: s.alt ?? 0,
      az: s.az ?? 0,
      range_km: s.range_km,
    });
  }
  for (const [id, track] of prev) {
    if (next.has(id)) continue;
    if (now - track.t0 < STALE_MS) next.set(id, track);
  }
  return next;
}

function overlayToPixel(x: number, y: number, fit: number, w: number, h: number): [number, number] {
  return [(0.5 + (x - 0.5) * fit) * w, (0.5 + (y - 0.5) * fit) * h];
}

function pixelToOverlay(px: number, py: number, fit: number, w: number, h: number): [number, number] {
  const f = fit || 1;
  return [(px / w - 0.5) / f + 0.5, (py / h - 0.5) / f + 0.5];
}

const spriteCache = new Map<string, HTMLCanvasElement>();

function tintedSatSprite(color: string, size: number): HTMLCanvasElement {
  const key = `${color}|${Math.round(size * 2)}`;
  const hit = spriteCache.get(key);
  if (hit) return hit;
  const pad = Math.max(8, Math.ceil(size * 1.4));
  const canvas = document.createElement("canvas");
  canvas.width = pad;
  canvas.height = pad;
  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  ctx.font = `${size}px "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(SAT_EMOJI, pad / 2, pad / 2 + size * 0.04);
  const img = ctx.getImageData(0, 0, pad, pad);
  const px = img.data;
  const r = Number.parseInt(color.slice(1, 3), 16);
  const g = Number.parseInt(color.slice(3, 5), 16);
  const b = Number.parseInt(color.slice(5, 7), 16);
  for (let i = 0; i < px.length; i += 4) {
    if (px[i + 3] === 0) continue;
    px[i] = r;
    px[i + 1] = g;
    px[i + 2] = b;
  }
  ctx.putImageData(img, 0, 0);
  spriteCache.set(key, canvas);
  return canvas;
}

function fmtKm(km: number) {
  return km >= 1000 ? km.toFixed(0) : km.toFixed(1);
}

export function SatIcon({ color }: { color: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const sprite = tintedSatSprite(color, 14);
    if (canvas.width !== sprite.width || canvas.height !== sprite.height) {
      canvas.width = sprite.width;
      canvas.height = sprite.height;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(sprite, 0, 0);
  }, [color]);
  return <canvas ref={ref} className="h-4 w-4" aria-hidden />;
}
