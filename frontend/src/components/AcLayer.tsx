import { useEffect, useRef } from "react";
import { AC_INBOUND, acColor, acPathStroke } from "@/components/AcInspector";
import { canvasDpr, overlayCenter, overlayRadiusPx, overlayToScreen, type OverlayView } from "@/lib/overlayView";
import {
  PSR_COLOR,
  PSR_PERIOD_S,
  SSR_COLOR,
  SSR_PERIOD_S,
  altMToFl,
  kmhToKt,
  psrEcho,
  ssrEcho,
  sweepAzimuth,
  sweepCrossed,
  vrateLetter,
} from "@/lib/radar";

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
  typecode?: string;
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

type RadarPaint = {
  id: string;
  x: number;
  y: number;
  heading?: number;
  groundKm?: number;
  gsKmh?: number;
  altM?: number;
  vrateMs?: number;
  name: string;
  category?: string;
  typecode?: string;
  pingAt: number;
  history: Array<{ x: number; y: number }>;
};

type DataTag = {
  id: string;
  name: string;
  altM?: number;
  gsKmh?: number;
  vrateMs?: number;
  typecode?: string;
  category?: string;
};

type Props = {
  samples: AcPt[];
  dt: number;
  iconScale: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMiss?: (clientX: number, clientY: number) => void;
  onPan?: (dx: number, dy: number) => void;
  onPanEnd?: () => void;
  view: OverlayView;
  liveView?: { current: OverlayView };
  gps?: boolean;
  ssr?: boolean;
  psr?: boolean;
  flightMode?: boolean;
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
  onPanEnd,
  view,
  liveView,
  gps = true,
  ssr = false,
  psr = false,
  flightMode = false,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPanRef = useRef(onPan);
  const onPanEndRef = useRef(onPanEnd);
  onPanRef.current = onPan;
  onPanEndRef.current = onPanEnd;
  const tracksRef = useRef(new Map<string, Track>());
  const scaleRef = useRef(iconScale);
  const viewRef = useRef(view);
  const liveViewRef = useRef(liveView);
  const selectedRef = useRef(selectedId);
  const onSelectRef = useRef(onSelect);
  const onMissRef = useRef(onMiss);
  const gpsRef = useRef(gps);
  const ssrRef = useRef(ssr);
  const psrRef = useRef(psr);
  const flightRef = useRef(flightMode);
  const ssrPaintRef = useRef(new Map<string, RadarPaint>());
  const psrPaintRef = useRef(new Map<string, RadarPaint>());
  const sweepRef = useRef({ ssr: 0, psr: 0 });
  const dtRef = useRef(dt);
  scaleRef.current = iconScale;
  dtRef.current = dt;
  viewRef.current = view;
  liveViewRef.current = liveView;
  selectedRef.current = selectedId;
  onSelectRef.current = onSelect;
  onMissRef.current = onMiss;
  gpsRef.current = gps;
  ssrRef.current = ssr;
  psrRef.current = psr;
  flightRef.current = flightMode;

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
    const cap = () => coastCap(dtRef.current);
    const rebase = () => {
      const now = performance.now();
      snapTracks(tracksRef.current, dtRef.current, now);
      sweepRef.current.ssr = sweepAzimuth(now, SSR_PERIOD_S);
      sweepRef.current.psr = sweepAzimuth(now, PSR_PERIOD_S);
      for (const paint of ssrPaintRef.current.values()) {
        const track = tracksRef.current.get(paint.id);
        if (!track) continue;
        paint.x = track.x0;
        paint.y = track.y0;
        paint.pingAt = now;
      }
      for (const paint of psrPaintRef.current.values()) {
        const track = tracksRef.current.get(paint.id);
        if (!track) continue;
        paint.x = track.x0;
        paint.y = track.y0;
        paint.pingAt = now;
      }
    };
    const draw = (now: number) => {
      if (document.hidden) {
        raf = 0;
        return;
      }
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      ctx.clearRect(0, 0, w, h);
      const viewNow = liveViewRef.current?.current ?? viewRef.current;
      const selected = selectedRef.current;
      const size = 11 * scaleRef.current;
      const pulse = 0.55 + 0.45 * Math.sin(now / 320);
      if (flightRef.current) drawFlightMode(ctx, viewNow);
      const ssrOn = ssrRef.current;
      const psrOn = psrRef.current;
      const gpsOn = gpsRef.current;
      if (!ssrOn) ssrPaintRef.current.clear();
      if (!psrOn) psrPaintRef.current.clear();
      if (ssrOn) {
        const az = sweepAzimuth(now, SSR_PERIOD_S);
        pingSweep(tracksRef.current, ssrPaintRef.current, sweepRef.current.ssr, az, now, cap());
        sweepRef.current.ssr = az;
        drawSweep(ctx, viewNow, az, SSR_COLOR, now, 0);
      }
      if (psrOn) {
        const az = sweepAzimuth(now, PSR_PERIOD_S);
        pingSweep(tracksRef.current, psrPaintRef.current, sweepRef.current.psr, az, now, cap());
        sweepRef.current.psr = az;
        drawSweep(ctx, viewNow, az, PSR_COLOR, now, 1);
      }
      for (const track of tracksRef.current.values()) {
        const inbound = Boolean(track.meta.inbound);
        const path = track.meta.path;
        if (gpsOn && path && path.length >= 2) {
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
      if (psrOn) drawPsrPaints(ctx, psrPaintRef.current, viewNow, now, selected, pulse);
      if (ssrOn) drawSsrPaints(ctx, ssrPaintRef.current, viewNow, now, selected, pulse, size);
      if (gpsOn) {
        for (const track of tracksRef.current.values()) {
          if (track.meta.rim) continue;
          const pos = coastPos(track, now, cap());
          const [px, py] = overlayToScreen(pos.x, pos.y, viewNow);
          if (px < -16 || py < -16 || px > w + 16 || py > h + 16) continue;
          const color = acColor(track.meta.ground_km);
          const ang =
            Math.hypot(track.vx, track.vy) > 1e-8 ? Math.atan2(track.vy, track.vx) + Math.PI / 2 : 0;
          if (track.id === selected) drawTargetRing(ctx, px, py, size, color, pulse);
          drawAirliner(ctx, px, py, ang, size, color, track.id === selected);
          drawDataBlock(ctx, tagFromTrack(track), px, py, size, 1, color);
        }
      }
      raf = window.requestAnimationFrame(draw);
    };
    const onVis = () => {
      if (document.hidden) {
        if (raf) window.cancelAnimationFrame(raf);
        raf = 0;
        return;
      }
      rebase();
      if (!raf) raf = window.requestAnimationFrame(draw);
    };
    document.addEventListener("visibilitychange", onVis);
    raf = window.requestAnimationFrame(draw);
    return () => {
      window.cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVis);
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
    const now = performance.now();
    const gpsOn = gpsRef.current;
    const ssrOn = ssrRef.current;
    const psrOn = psrRef.current;
    let best: Track | RadarPaint | null = null;
    let bestD = 32;
    let bestId: string | null = null;
    const consider = (id: string, px: number, py: number, obj: Track | RadarPaint) => {
      const d = Math.hypot(px - clickX, py - clickY);
      if (d < bestD) {
        bestD = d;
        best = obj;
        bestId = id;
      }
    };
    if (gpsOn) {
      for (const track of tracksRef.current.values()) {
        const pos = coastPos(track, now, coastCap(dtRef.current));
        const [px, py] = overlayToScreen(pos.x, pos.y, viewNow);
        consider(track.id, px, py, track);
        if (track.meta.from_x != null && track.meta.from_y != null) {
          const [fx, fy] = overlayToScreen(track.meta.from_x, track.meta.from_y, viewNow);
          consider(track.id, fx, fy, track);
        }
      }
    }
    if (ssrOn) {
      for (const paint of ssrPaintRef.current.values()) {
        const [px, py] = overlayToScreen(paint.x, paint.y, viewNow);
        consider(paint.id, px, py, paint);
      }
    }
    if (psrOn) {
      for (const paint of psrPaintRef.current.values()) {
        const [px, py] = overlayToScreen(paint.x, paint.y, viewNow);
        consider(paint.id, px, py, paint);
      }
    }
    if (best && bestId) {
      onSelectRef.current(bestId);
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
        if (drag?.moved) onPanEndRef.current?.();
        else hitTest(e.clientX, e.clientY);
      }}
      onPointerCancel={() => {
        if (dragRef.current?.moved) onPanEndRef.current?.();
        dragRef.current = null;
      }}
    />
  );
}

function coastCap(dt: number) {
  return Math.max(dt * 1.6, 1.2);
}

function coastPos(track: Track, now: number, cap?: number) {
  let age = (now - track.t0) / 1000;
  if (age < 0) age = 0;
  if (cap != null) age = Math.min(age, cap);
  return { x: track.x0 + track.vx * age, y: track.y0 + track.vy * age };
}

function sampleVel(s: AcPt, look: number) {
  return {
    vx: s.x2 != null ? (s.x2 - s.x) / look : 0,
    vy: s.y2 != null ? (s.y2 - s.y) / look : 0,
  };
}

function snapTracks(tracks: Map<string, Track>, dt: number, now: number) {
  const look = Math.max(dt, 1);
  for (const track of tracks.values()) {
    const { vx, vy } = sampleVel(track.meta, look);
    track.x0 = track.meta.x;
    track.y0 = track.meta.y;
    track.vx = vx;
    track.vy = vy;
    track.t0 = now;
  }
}

function sameMotion(a: AcPt, b: AcPt) {
  return a.x === b.x && a.y === b.y && a.x2 === b.x2 && a.y2 === b.y2;
}

function trackAzimuth(x: number, y: number) {
  return (Math.atan2(y - 0.5, x - 0.5) * (180 / Math.PI) + 90 + 360) % 360;
}

function pingSweep(
  tracks: Map<string, Track>,
  paints: Map<string, RadarPaint>,
  prevAz: number,
  nextAz: number,
  now: number,
  cap: number,
) {
  for (const track of tracks.values()) {
    if (track.meta.rim) continue;
    const pos = coastPos(track, now, cap);
    const az = trackAzimuth(pos.x, pos.y);
    const first = !paints.has(track.id);
    if (!first && !sweepCrossed(prevAz, nextAz, az)) continue;
    const prev = paints.get(track.id);
    const history = prev ? [...prev.history, { x: prev.x, y: prev.y }].slice(-22) : [];
    paints.set(track.id, {
      id: track.id,
      x: pos.x,
      y: pos.y,
      heading: track.meta.heading,
      groundKm: track.meta.ground_km,
      gsKmh: track.meta.gs_kmh,
      altM: track.meta.alt_m,
      vrateMs: track.meta.vrate_ms,
      name: track.name,
      category: track.meta.category,
      typecode: track.meta.typecode,
      pingAt: now,
      history,
    });
  }
  for (const id of [...paints.keys()]) {
    if (!tracks.has(id)) paints.delete(id);
  }
}

function drawSweep(
  ctx: CanvasRenderingContext2D,
  view: OverlayView,
  az: number,
  color: string,
  now: number,
  seed: number,
) {
  const [cx, cy] = overlayCenter(view);
  const R = overlayRadiusPx(view);
  const theta = ((az - 90) * Math.PI) / 180;
  const trail = 52;
  ctx.save();
  for (let i = trail; i >= 0; i--) {
    const a = ((az - i * 0.85 + 360) % 360) - 90;
    const t = (a * Math.PI) / 180;
    const fade = 1 - i / trail;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(t) * R, cy + Math.sin(t) * R);
    ctx.strokeStyle = color.replace("0.92", `${0.055 * fade * fade}`);
    ctx.lineWidth = i === 0 ? 2.4 : 14;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(theta) * R, cy + Math.sin(theta) * R);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.stroke();
  for (let i = 0; i < 28; i++) {
    const u = (i + 0.35) / 28;
    const wobble = Math.sin(now / 90 + i * 1.7 + seed * 4) * 0.012;
    const r = Math.max(0, Math.min(1, u + wobble)) * R;
    const px = cx + Math.cos(theta) * r;
    const py = cy + Math.sin(theta) * r;
    ctx.beginPath();
    ctx.arc(px, py, i % 4 === 0 ? 1.8 : 1.05, 0, Math.PI * 2);
    ctx.fillStyle = color.replace("0.92", `${0.18 + 0.55 * (1 - u)}`);
    ctx.fill();
  }
  ctx.restore();
}

function drawFlightMode(ctx: CanvasRenderingContext2D, view: OverlayView) {
  const [cx, cy] = overlayCenter(view);
  const R = overlayRadiusPx(view);
  ctx.save();
  ctx.strokeStyle = "rgba(45,212,191,0.28)";
  ctx.fillStyle = "rgba(165,243,252,0.55)";
  ctx.lineWidth = 1;
  for (const km of [10, 20, 40, 80]) {
    const r = R * (km / 80);
    ctx.setLineDash(km === 80 ? [] : [3, 5]);
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = "600 9px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(`${km} KM`, cx, cy - r + 2);
  }
  ctx.strokeStyle = "rgba(125,211,252,0.2)";
  ctx.setLineDash([2, 10]);
  for (let az = 0; az < 360; az += 30) {
    const t = ((az - 90) * Math.PI) / 180;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(t) * R * 0.08, cy + Math.sin(t) * R * 0.08);
    ctx.lineTo(cx + Math.cos(t) * R, cy + Math.sin(t) * R);
    ctx.stroke();
  }
  ctx.restore();
}

function paintDim(ageMs: number, periodS: number) {
  return 0.22 + 0.78 * Math.exp(-ageMs / 1000 / (periodS * 0.55));
}

function drawHistory(
  ctx: CanvasRenderingContext2D,
  paint: RadarPaint,
  view: OverlayView,
  color: string,
) {
  const raw = [...paint.history, { x: paint.x, y: paint.y }];
  const pts = raw.map((pt) => overlayToScreen(pt.x, pt.y, view));
  if (pts.length < 2) return;
  const n = pts.length;
  ctx.save();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < n; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.strokeStyle = color.replace("0.92", "0.18");
  ctx.lineWidth = 7;
  ctx.stroke();
  ctx.strokeStyle = color.replace("0.92", "0.42");
  ctx.lineWidth = 2.4;
  ctx.stroke();
  pts.slice(0, -1).forEach(([hx, hy], i) => {
    const t = (i + 1) / n;
    const r = 2.6 + t * 4.2;
    ctx.beginPath();
    ctx.arc(hx, hy, r * 2.1, 0, Math.PI * 2);
    ctx.fillStyle = color.replace("0.92", `${0.08 + t * 0.16}`);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(hx, hy, r, 0, Math.PI * 2);
    ctx.fillStyle = color.replace("0.92", `${0.22 + t * 0.5}`);
    ctx.fill();
  });
  ctx.restore();
}

function drawHeadingTick(
  ctx: CanvasRenderingContext2D,
  view: OverlayView,
  x: number,
  y: number,
  heading: number | undefined,
  color: string,
) {
  if (heading == null || !Number.isFinite(heading)) return;
  const [px, py] = overlayToScreen(x, y, view);
  const R = overlayRadiusPx(view);
  const pxPerKm = R / 80;
  const len = 10 * pxPerKm;
  const t = ((heading - 90) * Math.PI) / 180;
  ctx.save();
  ctx.setLineDash([5, 4]);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.15;
  ctx.beginPath();
  ctx.moveTo(px, py);
  ctx.lineTo(px + Math.cos(t) * len, py + Math.sin(t) * len);
  ctx.stroke();
  ctx.restore();
}

function drawSsrPaints(
  ctx: CanvasRenderingContext2D,
  paints: Map<string, RadarPaint>,
  view: OverlayView,
  now: number,
  selected: string | null,
  pulse: number,
  size: number,
) {
  for (const paint of paints.values()) {
    const age = now - paint.pingAt;
    const dim = paintDim(age, SSR_PERIOD_S);
    const echo = ssrEcho(paint.groundKm ?? 40);
    const alpha = Math.min(1, dim * (0.45 + 0.55 * echo));
    const [px, py] = overlayToScreen(paint.x, paint.y, view);
    const flash = age < 180 ? 1 : alpha;
    ctx.save();
    ctx.globalAlpha = flash;
    drawHistory(ctx, paint, view, SSR_COLOR);
    drawHeadingTick(ctx, view, paint.x, paint.y, paint.heading, SSR_COLOR);
    if (paint.id === selected) drawTargetRing(ctx, px, py, size, SSR_COLOR, pulse);
    const ping = age < 220;
    ctx.beginPath();
    ctx.arc(px, py, ping ? 7 : 4.2, 0, Math.PI * 2);
    ctx.fillStyle = ping ? "rgba(224,255,255,0.95)" : SSR_COLOR;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(px, py, ping ? 11 : 6.2, 0, Math.PI * 2);
    ctx.strokeStyle = SSR_COLOR;
    ctx.lineWidth = ping ? 2 : 1.2;
    ctx.stroke();
    drawDataBlock(ctx, tagFromPaint(paint), px, py, size, flash, SSR_COLOR);
    ctx.restore();
  }
}

function drawPsrPaints(
  ctx: CanvasRenderingContext2D,
  paints: Map<string, RadarPaint>,
  view: OverlayView,
  now: number,
  selected: string | null,
  pulse: number,
) {
  for (const paint of paints.values()) {
    const age = now - paint.pingAt;
    const dim = paintDim(age, PSR_PERIOD_S);
    const echo = psrEcho(paint.groundKm ?? 40);
    const alpha = Math.min(1, dim * echo);
    if (alpha < 0.05) continue;
    const [px, py] = overlayToScreen(paint.x, paint.y, view);
    ctx.save();
    ctx.globalAlpha = age < 160 ? 1 : alpha;
    drawHistory(ctx, paint, view, PSR_COLOR);
    drawHeadingTick(ctx, view, paint.x, paint.y, paint.heading, PSR_COLOR);
    const r = 2.4 + echo * 3.2;
    if (paint.id === selected) drawTargetRing(ctx, px, py, r + 4, PSR_COLOR, pulse);
    ctx.beginPath();
    ctx.arc(px, py, age < 160 ? r + 3 : r, 0, Math.PI * 2);
    ctx.fillStyle = PSR_COLOR;
    ctx.fill();
    drawDataBlock(ctx, tagFromPaint(paint), px, py, Math.max(r, 6), age < 160 ? 1 : alpha, PSR_COLOR);
    ctx.restore();
  }
}

function tagFromTrack(track: Track): DataTag {
  return {
    id: track.id,
    name: track.name,
    altM: track.meta.alt_m,
    gsKmh: track.meta.gs_kmh,
    vrateMs: track.meta.vrate_ms,
    typecode: track.meta.typecode,
    category: track.meta.category,
  };
}

function tagFromPaint(paint: RadarPaint): DataTag {
  return {
    id: paint.id,
    name: paint.name,
    altM: paint.altM,
    gsKmh: paint.gsKmh,
    vrateMs: paint.vrateMs,
    typecode: paint.typecode,
    category: paint.category,
  };
}

function tagLines(tag: DataTag): [string, string, string] {
  const fl = altMToFl(tag.altM);
  const kt = kmhToKt(tag.gsKmh);
  const trend = vrateLetter(tag.vrateMs);
  const callsign = (tag.name || tag.id || "----").trim().toUpperCase();
  const alt = fl != null ? String(fl).padStart(3, "0") : "---";
  const spd = kt != null ? Math.round(kt).toString().padStart(3, "0") : "---";
  const type =
    (tag.typecode || "").trim().toUpperCase() ||
    (tag.category && tag.category !== "Aircraft" ? tag.category : "") ||
    (tag.id || "").slice(0, 6).toUpperCase() ||
    "----";
  return [callsign, `${alt} ${trend} ${spd}`, type];
}

function drawDataBlock(
  ctx: CanvasRenderingContext2D,
  tag: DataTag,
  px: number,
  py: number,
  size: number,
  alpha: number,
  color: string,
) {
  const lines = tagLines(tag);
  const lineH = 13;
  const padX = 6;
  const padY = 4;
  ctx.save();
  ctx.globalAlpha = Math.max(0.15, alpha);
  ctx.font = "600 11px ui-monospace, SFMono-Regular, Menlo, monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  let boxW = 0;
  for (const line of lines) boxW = Math.max(boxW, ctx.measureText(line).width);
  boxW = Math.ceil(boxW) + padX * 2;
  const boxH = lines.length * lineH + padY * 2 - 2;
  const bx = Math.round(px + size * 1.55 + 12);
  const by = Math.round(py - boxH + 6);
  ctx.beginPath();
  ctx.moveTo(px + 5, py - 1);
  ctx.lineTo(bx - 2, by + Math.min(14, boxH * 0.4));
  ctx.strokeStyle = color;
  ctx.globalAlpha = Math.max(0.2, alpha * 0.7);
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.globalAlpha = Math.max(0.15, alpha);
  ctx.beginPath();
  if (typeof ctx.roundRect === "function") ctx.roundRect(bx, by, boxW, boxH, 3);
  else ctx.rect(bx, by, boxW, boxH);
  ctx.fillStyle = "rgba(4, 16, 24, 0.78)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.globalAlpha = Math.max(0.2, alpha * 0.55);
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.globalAlpha = Math.max(0.2, alpha);
  lines.forEach((line, i) => {
    drawHudLabel(ctx, line, bx + padX, by + padY + i * lineH, i === 0 ? "#f8fafc" : color, "left", "top");
  });
  ctx.restore();
}

function ingest(samples: AcPt[], dt: number, now: number, prev: Map<string, Track>): Map<string, Track> {
  const next = new Map<string, Track>();
  const look = Math.max(dt, 1);
  const catchup = Math.max(0.5, look * 0.7);
  for (const s of samples) {
    const id = s.id || s.icao24 || s.name || "";
    if (!id) continue;
    const old = prev.get(id);
    if (old && sameMotion(old.meta, s)) {
      next.set(id, { ...old, name: s.name || old.name, meta: s });
      continue;
    }
    const { vx, vy } = sampleVel(s, look);
    let x0 = s.x;
    let y0 = s.y;
    let ovx = vx;
    let ovy = vy;
    if (old) {
      const gap = (now - old.t0) / 1000;
      const pos = coastPos(old, now);
      const err = Math.hypot(s.x - pos.x, s.y - pos.y);
      const expected = Math.hypot(vx, vy) * look * 2 + 0.012;
      const stale = gap > look * 2 || err > expected || document.hidden;
      if (!stale) {
        x0 = pos.x;
        y0 = pos.y;
        ovx = (s.x + vx * catchup - pos.x) / catchup;
        ovy = (s.y + vy * catchup - pos.y) / catchup;
      }
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
