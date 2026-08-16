import { useEffect, useRef } from "react";
import { AC_INBOUND, acColor, acPathStroke } from "@/components/AcInspector";

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
  fit: number;
  iconScale: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMiss?: (clientX: number, clientY: number) => void;
  onPan?: (dx: number, dy: number) => void;
  viewZoom?: number;
};

const STALE_MS = 14000;

export default function AcLayer({
  samples,
  dt,
  fit,
  iconScale,
  selectedId,
  onSelect,
  onMiss,
  onPan,
  viewZoom = 1,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPanRef = useRef(onPan);
  onPanRef.current = onPan;
  const tracksRef = useRef(new Map<string, Track>());
  const dtRef = useRef(dt);
  const fitRef = useRef(fit);
  const scaleRef = useRef(iconScale);
  const zoomRef = useRef(viewZoom);
  const selectedRef = useRef(selectedId);
  const onSelectRef = useRef(onSelect);
  const onMissRef = useRef(onMiss);
  dtRef.current = dt;
  fitRef.current = fit;
  scaleRef.current = iconScale;
  zoomRef.current = viewZoom;
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
      const dpr = Math.min(window.devicePixelRatio || 1, 2, 4096 / Math.max(w, 1), 4096 / Math.max(h, 1));
      const bw = Math.max(1, Math.round(w * dpr));
      const bh = Math.max(1, Math.round(h * dpr));
      if (canvas.width === bw && canvas.height === bh) return;
      canvas.width = bw;
      canvas.height = bh;
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
      const fitNow = fitRef.current;
      const selected = selectedRef.current;
      const size = 11 * scaleRef.current * Math.min(1.6, Math.max(1, Math.sqrt(zoomRef.current)));
      const maxAge = Math.max(dtRef.current * 1.4, 4);
      const pulse = 0.55 + 0.45 * Math.sin(now / 320);
      for (const track of tracksRef.current.values()) {
        const inbound = Boolean(track.meta.inbound);
        const color = acColor(track.meta.alt, inbound);
        const path = track.meta.path;
        if (path && path.length >= 2) {
          ctx.beginPath();
          path.forEach((pt, i) => {
            const [x, y] = overlayToPixel(pt.x, pt.y, fitNow, w, h);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.strokeStyle = acPathStroke(color, inbound);
          ctx.lineWidth = inbound ? 1.6 : 1.2;
          ctx.setLineDash([5, 4]);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        if (inbound && track.meta.from_x != null && track.meta.from_y != null) {
          const [fx, fy] = overlayToPixel(track.meta.from_x, track.meta.from_y, fitNow, w, h);
          const [cx, cy] = overlayToPixel(0.5, 0.5, fitNow, w, h);
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
        const age = Math.min((now - track.t0) / 1000, maxAge);
        const x = track.x0 + track.vx * age;
        const y = track.y0 + track.vy * age;
        const [px, py] = overlayToPixel(x, y, fitNow, w, h);
        if (px < -16 || py < -16 || px > w + 16 || py > h + 16) continue;
        const inbound = Boolean(track.meta.inbound);
        const color = acColor(track.meta.alt, inbound);
        const ang = Math.hypot(track.vx, track.vy) > 1e-8 ? Math.atan2(track.vy, track.vx) + Math.PI / 2 : 0;
        drawAirliner(ctx, px, py, ang, size, color, track.id === selected);
        ctx.font = track.id === selected ? "700 12px ui-sans-serif, system-ui" : "600 11px ui-sans-serif, system-ui";
        ctx.textAlign = "left";
        ctx.textBaseline = "alphabetic";
        ctx.fillStyle = "#041018";
        ctx.fillText(track.name, px + size * 0.9, py - 4);
        ctx.fillStyle = color;
        ctx.fillText(track.name, px + size * 0.9 - 0.5, py - 4.5);
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
    const layoutW = canvas.clientWidth || rect.width;
    const layoutH = canvas.clientHeight || rect.height;
    const px = ((clientX - rect.left) / rect.width) * layoutW;
    const py = ((clientY - rect.top) / rect.height) * layoutH;
    const [ox, oy] = pixelToOverlay(px, py, fitRef.current, layoutW, layoutH);
    const now = performance.now();
    const maxAge = Math.max(dtRef.current * 1.4, 4);
    let best: Track | null = null;
    let bestD = 24 / Math.min(layoutW, layoutH);
    for (const track of tracksRef.current.values()) {
      const age = Math.min((now - track.t0) / 1000, maxAge);
      const x = track.x0 + track.vx * age;
      const y = track.y0 + track.vy * age;
      let d = Math.hypot(x - ox, y - oy);
      if (track.meta.from_x != null && track.meta.from_y != null) {
        d = Math.min(d, Math.hypot(track.meta.from_x - ox, track.meta.from_y - oy));
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

function overlayToPixel(x: number, y: number, fit: number, w: number, h: number): [number, number] {
  return [(0.5 + (x - 0.5) * fit) * w, (0.5 + (y - 0.5) * fit) * h];
}

function pixelToOverlay(px: number, py: number, fit: number, w: number, h: number): [number, number] {
  const f = fit || 1;
  return [(px / w - 0.5) / f + 0.5, (py / h - 0.5) / f + 0.5];
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
