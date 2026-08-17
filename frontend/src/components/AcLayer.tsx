import { useEffect, useRef } from "react";
import { AC_INBOUND, acColor, acPathStroke } from "@/components/AcInspector";
import { canvasDpr, overlayToScreen, type OverlayView } from "@/lib/overlayView";

export type AcPt = {
  x: number;
  y: number;
  x2?: number;
  y2?: number;
  id?: string;
  name?: string;
  icao24?: string;
  country?: string;
  alt?: number;
  az?: number;
  alt_m?: number;
  range_km?: number;
  ground_km?: number;
  gs_kmh?: number;
  heading?: number;
  vrate_ms?: number;
  squawk?: string;
  category?: string;
  cpa_km?: number;
  tca_s?: number;
  inbound?: boolean;
  rim?: boolean;
  from_x?: number;
  from_y?: number;
  path?: Array<{ x: number; y: number; alt?: number; ground_km?: number }>;
};

type Track = {
  id: string;
  name: string;
  x0: number;
  y0: number;
  vx: number;
  vy: number;
  t0: number;
  meta: AcPt;
};

type Props = {
  samples: AcPt[];
  dt: number;
  iconScale: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMiss?: (clientX: number, clientY: number) => void;
  onPan?: (dx: number, dy: number) => void;
  view: OverlayView;
};

const STALE_MS = 14000;

export default function AcLayer({
  samples,
  dt,
  iconScale,
  selectedId,
  onSelect,
  onMiss,
  onPan,
  view,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPanRef = useRef(onPan);
  onPanRef.current = onPan;
  const tracksRef = useRef(new Map<string, Track>());
  const dtRef = useRef(dt);
  const scaleRef = useRef(iconScale);
  const viewRef = useRef(view);
  const selectedRef = useRef(selectedId);
  const onSelectRef = useRef(onSelect);
  const onMissRef = useRef(onMiss);
  dtRef.current = dt;
  scaleRef.current = iconScale;
  viewRef.current = view;
  selectedRef.current = selectedId;
  onSelectRef.current = onSelect;
  onMissRef.current = onMiss;

  useEffect(() => {
    tracksRef.current = ingest(samples, dt, performance.now(), tracksRef.current);
  }, [samples, dt]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const wrap = canvas.parentElement;
    if (!wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
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
      const viewNow = viewRef.current;
      const selected = selectedRef.current;
      const size = 11 * scaleRef.current;
      const maxAge = Math.max(dtRef.current * 1.4, 4);
      const pulse = 0.55 + 0.45 * Math.sin(now / 320);
      for (const track of tracksRef.current.values()) {
        const inbound = Boolean(track.meta.inbound);
        const path = track.meta.path;
        if (path && path.length >= 2) {
          drawHeadingPath(ctx, path, viewNow, track.meta.ground_km, track.meta.gs_kmh);
        }
        if (inbound && track.meta.from_x != null && track.meta.from_y != null) {
          const [fx, fy] = overlayToScreen(track.meta.from_x, track.meta.from_y, viewNow);
          const [cx, cy] = overlayToScreen(0.5, 0.5, viewNow);
          const inward = Math.atan2(cy - fy, cx - fx);
          ctx.beginPath();
          ctx.arc(fx, fy, 5 + pulse * 3, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(74,222,128,${0.18 + pulse * 0.18})`;
          ctx.fill();
          ctx.beginPath();
          ctx.arc(fx, fy, 3.2, 0, Math.PI * 2);
          ctx.fillStyle = AC_INBOUND;
          ctx.fill();
          ctx.beginPath();
          ctx.moveTo(fx, fy);
          ctx.lineTo(fx + Math.cos(inward) * 10, fy + Math.sin(inward) * 10);
          ctx.strokeStyle = AC_INBOUND;
          ctx.lineWidth = 1.4;
          ctx.stroke();
        }
      }
      for (const track of tracksRef.current.values()) {
        if (track.meta.rim) continue;
        const age = Math.min((now - track.t0) / 1000, maxAge);
        const x = track.x0 + track.vx * age;
        const y = track.y0 + track.vy * age;
        const [px, py] = overlayToScreen(x, y, viewNow);
        if (px < -16 || py < -16 || px > w + 16 || py > h + 16) continue;
        const color = acColor(track.meta.ground_km);
        const ang = Math.hypot(track.vx, track.vy) > 1e-8 ? Math.atan2(track.vy, track.vx) + Math.PI / 2 : 0;
        if (track.id === selected) drawTargetRing(ctx, px, py, size, color, pulse);
        drawAirliner(ctx, px, py, ang, size, color, track.id === selected);
        ctx.font = track.id === selected ? "700 12px ui-sans-serif, system-ui" : "600 11px ui-sans-serif, system-ui";
        drawHudLabel(ctx, track.name, px + size * 0.9, py - 4, color);
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
    const viewNow = viewRef.current;
    const now = performance.now();
    const maxAge = Math.max(dtRef.current * 1.4, 4);
    let best: Track | null = null;
    let bestD = 32;
    for (const track of tracksRef.current.values()) {
      const age = Math.min((now - track.t0) / 1000, maxAge);
      const x = track.x0 + track.vx * age;
      const y = track.y0 + track.vy * age;
      const [px, py] = overlayToScreen(x, y, viewNow);
      let d = Math.hypot(px - clickX, py - clickY);
      if (track.meta.from_x != null && track.meta.from_y != null) {
        const [fx, fy] = overlayToScreen(track.meta.from_x, track.meta.from_y, viewNow);
        d = Math.min(d, Math.hypot(fx - clickX, fy - clickY));
      }
      if (d < bestD) {
        bestD = d;
        best = track;
      }
    }
    if (best) {
      onSelectRef.current(best.id);
      return;
    }
    onSelectRef.current(null);
    onMissRef.current?.(clientX, clientY);
  }

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full cursor-grab touch-none active:cursor-grabbing"
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
        if (!drag?.moved) hitTest(e.clientX, e.clientY);
      }}
      onPointerCancel={() => {
        dragRef.current = null;
      }}
    />
  );
}

function ingest(samples: AcPt[], dt: number, now: number, prev: Map<string, Track>): Map<string, Track> {
  const next = new Map<string, Track>();
  const look = Math.max(dt, 1);
  const catchup = Math.max(0.5, look * 0.7);
  for (const s of samples) {
    const id = s.id || s.icao24 || s.name || "";
    if (!id) continue;
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
      x0 = cx;
      y0 = cy;
      ovx = (s.x + vx * catchup - cx) / catchup;
      ovy = (s.y + vy * catchup - cy) / catchup;
    }
    next.set(id, { id, name: s.name || id, x0, y0, vx: ovx, vy: ovy, t0: now, meta: s });
  }
  for (const [id, track] of prev) {
    if (!next.has(id) && now - track.t0 < STALE_MS) next.set(id, track);
  }
  return next;
}

function drawHeadingPath(
  ctx: CanvasRenderingContext2D,
  path: Array<{ x: number; y: number; alt?: number; ground_km?: number }>,
  view: OverlayView,
  groundKm?: number,
  speedKmh?: number,
) {
  ctx.setLineDash([6, 4]);
  ctx.lineWidth = 1.65;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  let prev = overlayToScreen(path[0].x, path[0].y, view);
  let last = prev;
  for (let i = 1; i < path.length; i++) {
    const cur = overlayToScreen(path[i].x, path[i].y, view);
    const km = path[i].ground_km ?? path[i - 1].ground_km ?? groundKm;
    ctx.beginPath();
    ctx.moveTo(prev[0], prev[1]);
    ctx.lineTo(cur[0], cur[1]);
    ctx.strokeStyle = acPathStroke(acColor(km));
    ctx.stroke();
    prev = cur;
    last = cur;
  }
  ctx.setLineDash([]);
  if (speedKmh != null && Number.isFinite(speedKmh) && speedKmh > 0) {
    const label = `${Math.round(speedKmh)} km/h`;
    ctx.font = "600 10px ui-sans-serif, system-ui";
    drawHudLabel(ctx, label, last[0], last[1] - 3, acColor(path[path.length - 1]?.ground_km ?? groundKm), "center", "bottom");
  }
}

function drawHudLabel(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  color: string,
  align: CanvasTextAlign = "left",
  baseline: CanvasTextBaseline = "alphabetic",
) {
  const tx = Math.round(x);
  const ty = Math.round(y);
  ctx.save();
  ctx.setLineDash([]);
  ctx.textAlign = align;
  ctx.textBaseline = baseline;
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(4,16,24,0.75)";
  ctx.strokeText(text, tx, ty);
  ctx.fillStyle = color;
  ctx.fillText(text, tx, ty);
  ctx.restore();
}

function drawTargetRing(
  ctx: CanvasRenderingContext2D,
  px: number,
  py: number,
  size: number,
  color: string,
  pulse: number,
) {
  const r = size * 1.85 + pulse * 1.1;
  ctx.save();
  ctx.translate(px, py);
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(4,16,24,0.7)";
  ctx.lineWidth = 3.2;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.7;
  ctx.stroke();
  ctx.strokeStyle = "rgba(255,255,255,0.92)";
  ctx.lineWidth = 1.35;
  ctx.lineCap = "round";
  const gap = 0.28;
  for (let i = 0; i < 4; i++) {
    const a0 = (i * Math.PI) / 2 + gap;
    const a1 = ((i + 1) * Math.PI) / 2 - gap;
    ctx.beginPath();
    ctx.arc(0, 0, r + 5, a0, a1);
    ctx.stroke();
    const mid = (i * Math.PI) / 2;
    const c = Math.cos(mid);
    const s = Math.sin(mid);
    ctx.beginPath();
    ctx.moveTo(c * (r - 2), s * (r - 2));
    ctx.lineTo(c * (r + 8), s * (r + 8));
    ctx.stroke();
  }
  ctx.restore();
}

function drawAirliner(
  ctx: CanvasRenderingContext2D,
  px: number,
  py: number,
  ang: number,
  size: number,
  color: string,
  selected: boolean,
) {
  ctx.save();
  ctx.translate(px, py);
  ctx.rotate(ang);
  const s = size;
  ctx.fillStyle = color;
  ctx.strokeStyle = selected ? "rgba(255,255,255,0.95)" : "rgba(4,16,24,0.55)";
  ctx.lineWidth = selected ? 1.5 : 0.8;
  ctx.beginPath();
  ctx.moveTo(0, -s);
  ctx.lineTo(s * 0.16, -s * 0.35);
  ctx.lineTo(s * 0.13, s * 0.55);
  ctx.lineTo(0, s * 0.95);
  ctx.lineTo(-s * 0.13, s * 0.55);
  ctx.lineTo(-s * 0.16, -s * 0.35);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(s * 0.1, -s * 0.08);
  ctx.lineTo(s * 1.05, s * 0.28);
  ctx.lineTo(s * 0.78, s * 0.42);
  ctx.lineTo(s * 0.08, s * 0.16);
  ctx.lineTo(-s * 0.08, s * 0.16);
  ctx.lineTo(-s * 0.78, s * 0.42);
  ctx.lineTo(-s * 1.05, s * 0.28);
  ctx.lineTo(-s * 0.1, -s * 0.08);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(s * 0.07, s * 0.48);
  ctx.lineTo(s * 0.4, s * 0.78);
  ctx.lineTo(s * 0.22, s * 0.86);
  ctx.lineTo(0, s * 0.62);
  ctx.lineTo(-s * 0.22, s * 0.86);
  ctx.lineTo(-s * 0.4, s * 0.78);
  ctx.lineTo(-s * 0.07, s * 0.48);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}
