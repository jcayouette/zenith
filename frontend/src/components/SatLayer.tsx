import { useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { canvasDpr, overlayToScreen, type OverlayView } from "@/lib/overlayView";

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
  object_id?: string;
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
  iconScale: number;
  kinds: string[] | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onPan?: (dx: number, dy: number) => void;
  onPanEnd?: () => void;
  view: OverlayView;
  liveView?: { current: OverlayView };
  interactive?: boolean;
};

export type SatLayerHandle = {
  hitAt: (clientX: number, clientY: number) => void;
};

const STALE_MS = 1600;

const SatLayer = forwardRef<SatLayerHandle, Props>(function SatLayer(
  {
    samples,
    dt,
    iconScale,
    kinds,
    selectedId,
    onSelect,
    onPan,
    onPanEnd,
    view,
    liveView,
    interactive = true,
  },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPanRef = useRef(onPan);
  const onPanEndRef = useRef(onPanEnd);
  onPanRef.current = onPan;
  onPanEndRef.current = onPanEnd;
  const tracksRef = useRef(new Map<string, Track>());
  const dtRef = useRef(dt);
  const scaleRef = useRef(iconScale);
  const viewRef = useRef(view);
  const liveViewRef = useRef(liveView);
  const kindsRef = useRef(kinds);
  const selectedRef = useRef(selectedId);
  const onSelectRef = useRef(onSelect);

  dtRef.current = dt;
  scaleRef.current = iconScale;
  viewRef.current = view;
  liveViewRef.current = liveView;
  kindsRef.current = kinds;
  selectedRef.current = selectedId;
  onSelectRef.current = onSelect;

  useEffect(() => {
    tracksRef.current = ingest(samples, dt, performance.now(), tracksRef.current);
  }, [samples, dt]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      onSelectRef.current(null);
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
      if (w < 1 || h < 1) return;
      const dpr = canvasDpr(w, h);
      const bw = Math.max(1, Math.round(w * dpr));
      const bh = Math.max(1, Math.round(h * dpr));
      if (canvas.width !== bw || canvas.height !== bh) {
        canvas.width = bw;
        canvas.height = bh;
      }
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
      const viewNow = liveViewRef.current?.current ?? viewRef.current;
      const icon = scaleRef.current;
      const selected = selectedRef.current;
      const maxAge = Math.max(dtRef.current * 1.6, 1.2);
      for (const track of tracksRef.current.values()) {
        if (allow && !allow.has(track.kind) && track.id !== selected) continue;
        const age = Math.min((now - track.t0) / 1000, maxAge);
        const x = track.x0 + track.vx * age;
        const y = track.y0 + track.vy * age;
        const [px, py] = overlayToScreen(x, y, viewNow);
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
          ctx.font = track.id === selected ? "700 12px ui-sans-serif, system-ui" : "600 11px ui-sans-serif, system-ui";
          ctx.setLineDash([]);
          ctx.textAlign = "left";
          ctx.textBaseline = "alphabetic";
          ctx.lineJoin = "round";
          ctx.miterLimit = 2;
          ctx.lineWidth = 3;
          const tx = Math.round(px + size * 0.45);
          const ty = Math.round(py - 6);
          ctx.strokeStyle = "rgba(4,16,24,0.75)";
          ctx.strokeText(track.name, tx, ty);
          ctx.fillStyle = color;
          ctx.fillText(track.name, tx, ty);
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
    if (rect.width < 1 || rect.height < 1) return;
    const clickX = clientX - rect.left;
    const clickY = clientY - rect.top;
    const viewNow = liveViewRef.current?.current ?? viewRef.current;
    const allow = kindsRef.current ? new Set(kindsRef.current) : null;
    const now = performance.now();
    const maxAge = Math.max(dtRef.current * 1.6, 1.2);
    let best: Track | null = null;
    let bestD = 28;
    for (const track of tracksRef.current.values()) {
      if (allow && !allow.has(track.kind)) continue;
      const age = Math.min((now - track.t0) / 1000, maxAge);
      const x = track.x0 + track.vx * age;
      const y = track.y0 + track.vy * age;
      const [px, py] = overlayToScreen(x, y, viewNow);
      const d = Math.hypot(px - clickX, py - clickY);
      const pad = track.kind === "station" ? 1.8 : 1.35;
      if (d < bestD * pad) {
        bestD = d;
        best = { ...track, x0: x, y0: y };
      }
    }
    if (!best) {
      onSelectRef.current(null);
      return;
    }
    onSelectRef.current(best.id);
  }

  useImperativeHandle(ref, () => ({
    hitAt(clientX: number, clientY: number) {
      hitTest(clientX, clientY);
    },
  }));

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 h-full w-full touch-none ${
        interactive ? "cursor-grab active:cursor-grabbing" : "pointer-events-none"
      }`}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        dragRef.current = { x: e.clientX, y: e.clientY, moved: false };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const drag = dragRef.current;
        if (!drag) return;
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) < 4) return;
        drag.moved = true;
        drag.x = e.clientX;
        drag.y = e.clientY;
        onPanRef.current?.(dx, dy);
      }}
      onPointerUp={(e) => {
        const drag = dragRef.current;
        dragRef.current = null;
        e.currentTarget.releasePointerCapture(e.pointerId);
        if (drag?.moved) onPanEndRef.current?.();
        else hitTest(e.clientX, e.clientY);
      }}
      onPointerCancel={() => {
        if (dragRef.current?.moved) onPanEndRef.current?.();
        dragRef.current = null;
      }}
    />
  );
});

export default SatLayer;

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
