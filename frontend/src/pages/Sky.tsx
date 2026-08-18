import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import AcInspector, { type AcMeta } from "@/components/AcInspector";
import AcLayer, { type AcPt } from "@/components/AcLayer";
import GroundMap, { type MapStyle } from "@/components/GroundMap";
import LiveFrame from "@/components/LiveFrame";
import SatInspector, { type Satcat } from "@/components/SatInspector";
import SatLayer, { satKindOf, type SatLayerHandle } from "@/components/SatLayer";
import SkyToolbar, { type PanelId, type SkyConfig } from "@/components/SkyToolbar";
import { EMPTY_VIEW, type OverlayView } from "@/lib/overlayView";
import type { Telemetry } from "@/lib/utils";

type Pt = {
  x: number;
  y: number;
  alt?: number;
  az?: number;
  name?: string;
  mag?: number;
  x2?: number;
  y2?: number;
  norad?: string;
  kind?: string;
  range_km?: number;
  object_id?: string;
};

type Constellation = {
  id: string;
  name: string;
  lines: Pt[][];
  label?: Pt;
};

type Pass = {
  name: string;
  start: string;
  peak: string;
  end: string;
  max_alt: number;
  az_peak: number;
};

type SkyPayload = {
  when: string;
  width: number;
  height: number;
  horizon?: number;
  projected_horizon?: number;
  layers: Record<string, boolean>;
  sun: Pt & { name: string; visible: boolean };
  moon: Pt & { name: string; visible: boolean };
  stars: Pt[];
  constellations: Constellation[];
  asterisms: Constellation[];
  star_names: Pt[];
  grid: Array<{ kind: string; alt?: number; az?: number; points: Pt[]; label?: Pt }>;
  satellites: Pt[];
  passes: Pass[];
  error: string | null;
  needs_location?: boolean;
  line_width?: number;
  tle_count?: number;
  dt?: number;
};

type SettingsValues = {
  sky?: Partial<SkyConfig>;
  location?: {
    latitude?: number;
    longitude?: number;
    keogram_angle_deg?: number;
    name?: string;
    address?: string;
    city?: string;
    postcode?: string;
  };
};

const SKY_DEFAULTS: SkyConfig = {
  constellations: true,
  constellation_names: true,
  asterisms: true,
  star_names: true,
  grid: false,
  planets: true,
  satellites: true,
  aircraft: true,
  map: false,
  site_label: true,
  map_brightness: 0.62,
  map_style: "street" as MapStyle,
  mag_limit: 5,
  star_name_mag: 1.85,
  min_sat_alt_deg: 0,
  sat_icon_scale: 1,
  horizon: 1,
  constellation_line_px: 1,
  simulator_catalog: true,
};

const emptyTel = { mode: "—", sun_alt: 0, backend: "—", error: null as string | null, camera: true };
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 256;

export default function Sky() {
  const client = useQueryClient();
  const [image, setImage] = useState("");
  const [tel, setTel] = useState(emptyTel);
  const [sky, setSky] = useState<SkyPayload | null>(null);
  const [liveSats, setLiveSats] = useState<Pt[] | null>(null);
  const [satDt, setSatDt] = useState(1);
  const [selectedSat, setSelectedSat] = useState<string | null>(null);
  const [selectedAc, setSelectedAc] = useState<string | null>(null);
  const [liveAc, setLiveAc] = useState<AcPt[] | null>(null);
  const [acDt, setAcDt] = useState(8);
  const [acError, setAcError] = useState<string | null>(null);
  const [acMeta, setAcMeta] = useState<AcMeta | null>(null);
  const [acMetaLoading, setAcMetaLoading] = useState(false);
  const satLayerRef = useRef<SatLayerHandle>(null);
  const [satcat, setSatcat] = useState<Satcat | null>(null);
  const [satcatLoading, setSatcatLoading] = useState(false);
  const refetchTimer = useRef(0);
  const commitTimer = useRef(0);
  const patchTimer = useRef(0);
  const patchGen = useRef(0);
  const draftRef = useRef<Partial<SkyConfig>>({});
  const reloadAfterPatch = useRef(false);
  const [draftRev, setDraftRev] = useState(0);
  const [satKinds, setSatKinds] = useState<string[] | null>(null);
  const [panel, setPanel] = useState<PanelId | null>(null);
  const [trackGps, setTrackGps] = useState(true);
  const [trackSsr, setTrackSsr] = useState(false);
  const [trackPsr, setTrackPsr] = useState(false);
  const [flightMode, setFlightMode] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [stageSize, setStageSize] = useState({ w: 0, h: 0 });
  const [fullscreen, setFullscreen] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef(1);
  const panRef = useRef({ x: 0, y: 0 });
  const panRafRef = useRef<number | null>(null);
  const zoomRafRef = useRef<number | null>(null);
  const boxRef = useRef({ w: 0, h: 0 });
  const stageSizeRef = useRef({ w: 0, h: 0 });
  const fitRef = useRef(1);
  const overlayViewRef = useRef<OverlayView>(EMPTY_VIEW);
  const worldRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const cssFullRef = useRef(false);
  const livePanRef = useRef(false);
  const liveZoomRef = useRef(false);
  const zoomIdleRef = useRef(0);
  if (liveZoomRef.current && zoom === zoomRef.current) liveZoomRef.current = false;
  if (!liveZoomRef.current && zoomRafRef.current == null) zoomRef.current = zoom;
  if (!livePanRef.current && panRafRef.current == null) panRef.current = pan;
  boxRef.current = box;
  stageSizeRef.current = stageSize;

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => fetch("/api/settings").then((r) => r.json() as Promise<SettingsValues>),
  });
  const cfg: SkyConfig = { ...SKY_DEFAULTS, ...settingsQuery.data?.sky, ...draftRef.current };
  void draftRev;

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/ws/live`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as { image: string; telemetry: Telemetry };
      setImage(msg.image);
      setTel({
        mode: msg.telemetry.mode,
        sun_alt: msg.telemetry.sun_alt,
        backend: msg.telemetry.backend,
        error: msg.telemetry.error,
        camera: msg.telemetry.camera !== false,
      });
    };
    return () => ws.close();
  }, []);

  async function loadSky() {
    const res = await fetch("/api/sky");
    if (!res.ok) return;
    setSky((await res.json()) as SkyPayload);
  }

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        if (!stop) await loadSky();
      } catch {
        /* ignore */
      }
    }
    void tick();
    const id = window.setInterval(() => void tick(), 4000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!cfg.satellites) {
      setLiveSats([]);
      return;
    }
    let stop = false;
    async function tick() {
      try {
        const res = await fetch("/api/sky/sats");
        if (!res.ok || stop) return;
        const data = (await res.json()) as { satellites?: Pt[]; dt?: number };
        if (stop) return;
        setLiveSats(data.satellites ?? []);
        if (data.dt && data.dt > 0) setSatDt(data.dt);
      } catch {
        /* keep last */
      }
    }
    void tick();
    const id = window.setInterval(() => void tick(), 1000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [cfg.satellites, cfg.min_sat_alt_deg]);

  useEffect(() => {
    if (!cfg.aircraft) {
      setLiveAc([]);
      setAcError(null);
      return;
    }
    let stop = false;
    async function tick() {
      try {
        const res = await fetch("/api/sky/aircraft");
        if (!res.ok || stop) return;
        const data = (await res.json()) as { aircraft?: AcPt[]; dt?: number; error?: string | null };
        if (stop) return;
        setLiveAc(data.aircraft ?? []);
        if (data.dt && data.dt > 0) setAcDt(data.dt);
        setAcError(data.error ?? null);
      } catch {
        /* keep last */
      }
    }
    void tick();
    const id = window.setInterval(() => void tick(), 3000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [cfg.aircraft]);

  useEffect(() => {
    const onFs = () => setFullscreen(Boolean(document.fullscreenElement) || cssFullRef.current);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const aspect = (sky?.width || 4) / (sky?.height || 3);
    const measure = () => {
      const sw = stage.clientWidth;
      const sh = stage.clientHeight;
      if (sw < 8 || sh < 8) return;
      setStageSize({ w: sw, h: sh });
      if (sw / sh > aspect) {
        const h = sh;
        setBox({ w: h * aspect, h });
      } else {
        const w = sw;
        setBox({ w, h: w / aspect });
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(stage);
    return () => ro.disconnect();
  }, [sky?.width, sky?.height, fullscreen]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomBy(wheelFactor(zoomRef.current, e.deltaY < 0));
    };
    stage.addEventListener("wheel", onWheel, { passive: false });
    return () => stage.removeEventListener("wheel", onWheel);
  }, []);

  function makeView(z: number, p: { x: number; y: number }): OverlayView {
    const { w, h } = boxRef.current;
    const sw = stageSizeRef.current.w;
    const sh = stageSizeRef.current.h;
    const width = w * z;
    const height = h * z;
    return {
      left: (sw - width) / 2 + p.x,
      top: (sh - height) / 2 + p.y,
      width,
      height,
      fit: fitRef.current,
    };
  }

  function applyTransforms(z: number, p: { x: number; y: number }) {
    const v = makeView(z, p);
    overlayViewRef.current = v;
    const t = `translate(${v.left}px, ${v.top}px) scale(${z})`;
    if (worldRef.current) worldRef.current.style.transform = t;
    if (gridRef.current) gridRef.current.style.transform = t;
  }

  function scheduleZoomCommit() {
    liveZoomRef.current = true;
    window.clearTimeout(zoomIdleRef.current);
    zoomIdleRef.current = window.setTimeout(() => {
      zoomIdleRef.current = 0;
      setZoom(zoomRef.current);
      setPan(panRef.current);
    }, 180);
  }

  function zoomAt(cx: number, cy: number, factor: number) {
    const stage = stageRef.current;
    if (!stage) return;
    const prev = zoomRef.current;
    const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev * factor));
    if (next === prev) return;
    const { w, h } = boxRef.current;
    const sw = stage.clientWidth;
    const sh = stage.clientHeight;
    const p = panRef.current;
    const left = (sw - w * prev) / 2 + p.x;
    const top = (sh - h * prev) / 2 + p.y;
    const wx = (cx - left) / prev;
    const wy = (cy - top) / prev;
    const nx = cx - (sw - w * next) / 2 - wx * next;
    const ny = cy - (sh - h * next) / 2 - wy * next;
    zoomRef.current = next;
    panRef.current = { x: nx, y: ny };
    applyTransforms(next, panRef.current);
    scheduleZoomCommit();
  }

  function zoomBy(factor: number) {
    const stage = stageRef.current;
    if (!stage) return;
    const { w, h } = boxRef.current;
    const z = zoomRef.current;
    const p = panRef.current;
    const siteX = (stage.clientWidth - w * z) / 2 + p.x + (w * z) / 2;
    const siteY = (stage.clientHeight - h * z) / 2 + p.y + (h * z) / 2;
    zoomAt(siteX, siteY, factor);
  }

  function resetView() {
    livePanRef.current = false;
    liveZoomRef.current = false;
    window.clearTimeout(zoomIdleRef.current);
    zoomIdleRef.current = 0;
    if (panRafRef.current != null) window.cancelAnimationFrame(panRafRef.current);
    if (zoomRafRef.current != null) window.cancelAnimationFrame(zoomRafRef.current);
    panRafRef.current = null;
    zoomRafRef.current = null;
    zoomRef.current = 1;
    panRef.current = { x: 0, y: 0 };
    applyTransforms(1, panRef.current);
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  function centerView() {
    livePanRef.current = false;
    liveZoomRef.current = false;
    window.clearTimeout(zoomIdleRef.current);
    zoomIdleRef.current = 0;
    if (panRafRef.current != null) window.cancelAnimationFrame(panRafRef.current);
    panRafRef.current = null;
    panRef.current = { x: 0, y: 0 };
    applyTransforms(zoomRef.current, panRef.current);
    setPan({ x: 0, y: 0 });
  }

  function shiftPan(dx: number, dy: number) {
    livePanRef.current = true;
    panRef.current = { x: panRef.current.x + dx, y: panRef.current.y + dy };
    applyTransforms(zoomRef.current, panRef.current);
  }

  function endPan() {
    livePanRef.current = false;
    if (panRafRef.current != null) window.cancelAnimationFrame(panRafRef.current);
    panRafRef.current = null;
    setPan(panRef.current);
  }

  async function toggleFullscreen() {
    const el = stageRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      cssFullRef.current = false;
      await document.exitFullscreen().catch(() => undefined);
      setFullscreen(false);
      return;
    }
    try {
      await el.requestFullscreen();
      setFullscreen(true);
    } catch {
      cssFullRef.current = !cssFullRef.current;
      setFullscreen(cssFullRef.current);
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "+" || e.key === "=") zoomBy(1.15);
      if (e.key === "-" || e.key === "_") zoomBy(1 / 1.15);
      if (e.key === "0") resetView();
      if (e.key === "c" || e.key === "C") centerView();
      if (e.key === "f" || e.key === "F") void toggleFullscreen();
      if (e.key === "Escape") {
        setPanel(null);
        setSelectedSat(null);
        setSelectedAc(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function queueSkyReload() {
    window.clearTimeout(refetchTimer.current);
    refetchTimer.current = window.setTimeout(() => void loadSky(), 120);
  }

  function queueCommit() {
    window.clearTimeout(commitTimer.current);
    commitTimer.current = window.setTimeout(() => {
      void fetch("/api/settings/commit", { method: "POST" });
    }, 400);
  }

  async function flushSkyPatch() {
    const pending = { ...draftRef.current };
    if (!Object.keys(pending).length) {
      if (reloadAfterPatch.current) {
        reloadAfterPatch.current = false;
        queueSkyReload();
      }
      return;
    }
    const gen = ++patchGen.current;
    const reload = reloadAfterPatch.current;
    reloadAfterPatch.current = false;
    try {
      const res = await fetch("/api/settings/live", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sky: pending }),
      });
      if (!res.ok) return;
      const data = (await res.json()) as SettingsValues;
      if (gen !== patchGen.current) return;
      client.setQueryData(["settings"], {
        ...data,
        sky: { ...SKY_DEFAULTS, ...data.sky, ...draftRef.current },
      });
      const next: Partial<SkyConfig> = { ...draftRef.current };
      (Object.keys(pending) as (keyof SkyConfig)[]).forEach((key) => {
        if (next[key] === pending[key]) delete next[key];
      });
      draftRef.current = next;
    } catch {
      /* keep draft */
    }
    queueCommit();
    if (reload) queueSkyReload();
  }

  function patchSky(partial: Partial<SkyConfig>, reload = false) {
    draftRef.current = { ...draftRef.current, ...partial };
    setDraftRev((n) => n + 1);
    if (reload) reloadAfterPatch.current = true;
    window.clearTimeout(patchTimer.current);
    patchTimer.current = window.setTimeout(() => void flushSkyPatch(), 70);
  }

  function commitSlider() {
    window.clearTimeout(patchTimer.current);
    void flushSkyPatch();
  }

  const lineWidth = cfg.constellation_line_px;
  const bake = sky?.projected_horizon ?? sky?.horizon ?? 1;
  const fit = bake > 0 ? cfg.horizon / bake : 1;
  fitRef.current = fit;
  const loc = settingsQuery.data?.location;
  const hasSite = Boolean(loc) && !(loc?.latitude === 0 && loc?.longitude === 0);
  const siteLat = hasSite ? (loc?.latitude ?? null) : null;
  const siteLon = hasSite ? (loc?.longitude ?? null) : null;
  const northAngle = loc?.keogram_angle_deg ?? 0;
  const siteName = loc?.name?.trim() || "";
  const siteCity = loc?.city?.trim() || "";
  const overlayStars = useMemo(
    () => (cfg.star_names ? (sky?.stars ?? []).filter((s) => magVisible(s.mag, cfg.mag_limit)) : []),
    [sky, cfg.star_names, cfg.mag_limit],
  );
  const namedStars = useMemo(
    () => (cfg.star_names ? (sky?.star_names ?? []).filter((s) => magVisible(s.mag, cfg.star_name_mag)) : []),
    [sky, cfg.star_names, cfg.star_name_mag],
  );
  const visibleConstellations = useMemo(
    () => filterFigures(sky?.constellations ?? [], cfg.mag_limit),
    [sky, cfg.mag_limit],
  );
  const visibleAsterisms = useMemo(
    () => filterFigures(sky?.asterisms ?? [], cfg.mag_limit),
    [sky, cfg.mag_limit],
  );
  const sats = liveSats ?? sky?.satellites ?? [];
  const filteredSats = useMemo(() => {
    if (!satKinds) return sats;
    const allow = new Set(satKinds);
    return sats.filter((s) => allow.has(satKindOf(s)));
  }, [sats, satKinds]);
  const kindCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const s of sats) {
      const kind = satKindOf(s);
      counts[kind] = (counts[kind] ?? 0) + 1;
    }
    return counts;
  }, [sats]);
  const nowList = useMemo(() => {
    const rank = (kind?: string) =>
      kind === "station" ? -1 : kind === "starlink" || kind === "oneweb" ? 2 : 0;
    return [...filteredSats]
      .sort((a, b) => rank(a.kind) - rank(b.kind) || (b.alt ?? 0) - (a.alt ?? 0))
      .slice(0, 12);
  }, [filteredSats]);
  const pickedSat = useMemo(
    () => (selectedSat ? sats.find((s) => (s.norad || s.name) === selectedSat) ?? null : null),
    [sats, selectedSat],
  );
  const planes = liveAc ?? [];
  const pickedAc = useMemo(
    () => (selectedAc ? planes.find((p) => (p.id || p.icao24) === selectedAc) ?? null : null),
    [planes, selectedAc],
  );

  useEffect(() => {
    const norad = pickedSat?.norad;
    if (!selectedSat || !norad) {
      setSatcat(null);
      setSatcatLoading(false);
      return;
    }
    const kind = pickedSat?.kind ?? "";
    const satName = pickedSat?.name ?? "";
    let stop = false;
    setSatcatLoading(true);
    setSatcat(null);
    const qs = new URLSearchParams();
    if (kind) qs.set("kind", kind);
    if (satName) qs.set("name", satName);
    const query = qs.size ? `?${qs}` : "";
    void fetch(`/api/sky/satcat/${encodeURIComponent(norad)}${query}`)
      .then((res) => (res.ok ? res.json() : { norad, error: "No SATCAT record" }))
      .then((data: Satcat) => {
        if (!stop) setSatcat(data);
      })
      .catch(() => {
        if (!stop) setSatcat({ norad, error: "Catalog unavailable" });
      })
      .finally(() => {
        if (!stop) setSatcatLoading(false);
      });
    return () => {
      stop = true;
    };
  }, [selectedSat, pickedSat?.norad, pickedSat?.kind, pickedSat?.name]);

  useEffect(() => {
    const icao = pickedAc?.icao24 || pickedAc?.id;
    if (!selectedAc || !icao) {
      setAcMeta(null);
      setAcMetaLoading(false);
      return;
    }
    let stop = false;
    setAcMetaLoading(true);
    setAcMeta(null);
    const callsign = pickedAc?.name?.trim();
    const qs = callsign ? `?callsign=${encodeURIComponent(callsign)}` : "";
    void fetch(`/api/sky/aircraft/${encodeURIComponent(icao)}${qs}`)
      .then((res) => (res.ok ? res.json() : { icao24: icao, error: "No aircraft type record" }))
      .then((data: AcMeta) => {
        if (!stop) setAcMeta(data);
      })
      .catch(() => {
        if (!stop) setAcMeta({ icao24: icao, error: "Type lookup unavailable" });
      })
      .finally(() => {
        if (!stop) setAcMetaLoading(false);
      });
    return () => {
      stop = true;
    };
  }, [selectedAc, pickedAc?.icao24, pickedAc?.id, pickedAc?.name]);

  const status = [
    tel.backend,
    tel.mode,
    Number.isFinite(tel.sun_alt) ? `sun ${tel.sun_alt >= 0 ? "+" : ""}${tel.sun_alt.toFixed(1)}°` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  const worldW = box.w || stageSize.w;
  const worldH = box.h || stageSize.h;
  const zNow = zoomRef.current;
  const pNow = panRef.current;
  const scaledW = worldW * zNow;
  const scaledH = worldH * zNow;
  const worldLeft = (stageSize.w - scaledW) / 2 + pNow.x;
  const worldTop = (stageSize.h - scaledH) / 2 + pNow.y;
  const overlayView: OverlayView = {
    left: worldLeft,
    top: worldTop,
    width: scaledW,
    height: scaledH,
    fit,
  };
  overlayViewRef.current = overlayView;
  const hudFont = 12 / Math.max(scaledW * fit, 1);
  const hudFontLg = 14 / Math.max(scaledW * fit, 1);
  const pinR = 4.5 / Math.max(scaledW * fit, 1);
  const pinLen = 9 / Math.max(scaledW * fit, 1);
  const worldStyle = {
    left: 0,
    top: 0,
    width: worldW || "100%",
    height: worldH || "100%",
    transform: `translate(${worldLeft}px, ${worldTop}px) scale(${zNow})`,
    transformOrigin: "0 0",
    willChange: "transform",
  } as const;

  function onGrabPointerDown(e: ReactPointerEvent) {
    if (e.button !== 0) return;
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    const drag = { x: e.clientX, y: e.clientY };
    function move(ev: PointerEvent) {
      shiftPan(ev.clientX - drag.x, ev.clientY - drag.y);
      drag.x = ev.clientX;
      drag.y = ev.clientY;
    }
    function up() {
      el.releasePointerCapture(e.pointerId);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      endPan();
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <div
      ref={stageRef}
      className={`sky-stage relative overflow-hidden bg-black touch-none ${
        fullscreen
          ? `h-full w-full rounded-none ${document.fullscreenElement ? "" : "fixed inset-0 z-50"}`
          : "aspect-4/3 w-full rounded-3xl frame-glow"
      }`}
    >
      <div ref={worldRef} className="absolute z-0" style={worldStyle}>
        {image ? (
          <LiveFrame
            src={image}
            alt="All-sky with catalog overlay"
            className="pointer-events-none absolute inset-0 h-full w-full select-none object-fill"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-white/40">Waiting for live frame…</div>
        )}
      </div>
      {cfg.map && siteLat != null && siteLon != null && stageSize.w > 8 && overlayView.width > 8 ? (
        <div className="absolute inset-0 z-[1] overflow-hidden pointer-events-none">
          <GroundMap
            view={overlayView}
            viewRef={overlayViewRef}
            stageW={stageSize.w}
            stageH={stageSize.h}
            brightness={cfg.map_brightness}
            lat={siteLat}
            lon={siteLon}
            northAngle={northAngle}
            mapKm={80}
            basemap={(cfg.map_style as MapStyle) || "street"}
          />
        </div>
      ) : null}
      {sky ? (
        <div ref={gridRef} className="absolute z-[2] pointer-events-none" style={worldStyle}>
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 1 1"
            preserveAspectRatio="none"
          >
            <g transform={`translate(0.5 0.5) scale(${fit}) translate(-0.5 -0.5)`}>
            {overlayStars.map((s, i) => (
              <circle
                key={`st-${i}`}
                cx={s.x}
                cy={s.y}
                r={starRadius(s.mag ?? 5)}
                fill="rgba(255,248,235,0.92)"
              />
            ))}
            {cfg.grid
              ? sky.grid.map((g, i) =>
                  g.points.length >= 2 ? (
                    <polyline
                      key={`g-${g.kind}-${g.alt ?? g.az}-${i}`}
                      fill="none"
                      stroke="rgba(200,231,255,0.22)"
                      strokeWidth={Math.max(0.5, lineWidth * 0.65)}
                      vectorEffect="non-scaling-stroke"
                      points={g.points.map((p) => `${p.x},${p.y}`).join(" ")}
                    />
                  ) : null,
                )
              : null}
            {cfg.map || cfg.grid || cfg.site_label ? (
              <g>
                <line
                  x1={0.5 - pinLen}
                  y1={0.5}
                  x2={0.5 + pinLen}
                  y2={0.5}
                  stroke="rgba(251,191,36,0.95)"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                />
                <line
                  x1={0.5}
                  y1={0.5 - pinLen}
                  x2={0.5}
                  y2={0.5 + pinLen}
                  stroke="rgba(251,191,36,0.95)"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                />
                <circle
                  cx={0.5}
                  cy={0.5}
                  r={pinR}
                  fill="rgba(251,191,36,0.35)"
                  stroke="rgba(248,250,252,0.95)"
                  strokeWidth="1.25"
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            ) : null}
            {cfg.site_label && (siteName || siteCity) ? (
              <g opacity="0.9" style={{ fontFamily: "inherit" }}>
                <line
                  x1={0.5}
                  y1={0.5 + pinLen * 1.4}
                  x2={0.5}
                  y2={0.521}
                  stroke="rgba(200,231,255,0.4)"
                  strokeWidth="1"
                  vectorEffect="non-scaling-stroke"
                />
                {siteName ? (
                  <text
                    x={0.5}
                    y={0.524}
                    fill="rgba(226,239,255,0.82)"
                    fontSize={hudFont}
                    fontWeight={500}
                    textAnchor="middle"
                    dominantBaseline="hanging"
                    style={{ letterSpacing: "0.16em" }}
                  >
                    {siteName}
                  </text>
                ) : null}
                {siteCity ? (
                  <text
                    x={0.5}
                    y={siteName ? 0.535 : 0.524}
                    fill="rgba(200,231,255,0.5)"
                    fontSize={hudFont * 0.85}
                    fontWeight={400}
                    textAnchor="middle"
                    dominantBaseline="hanging"
                    style={{ letterSpacing: "0.28em" }}
                  >
                    {siteCity.toUpperCase()}
                  </text>
                ) : null}
              </g>
            ) : null}
            {cfg.grid
              ? sky.grid.map((g, i) => {
                  const label = gridDegreeLabel(g);
                  if (!label) return null;
                  const alt = g.kind === "alt" || g.kind === "zenith";
                  return (
                    <text
                      key={`gl-${g.kind}-${g.alt ?? g.az}-${i}`}
                      x={label.x}
                      y={label.y}
                      fill={alt ? "rgba(200,231,255,0.88)" : "rgba(200,231,255,0.72)"}
                      fontSize={alt ? hudFontLg : hudFont}
                      fontWeight={alt ? 600 : 400}
                      textAnchor="middle"
                      dominantBaseline="middle"
                    >
                      {label.text}
                    </text>
                  );
                })
              : null}
            {cfg.constellations
              ? visibleConstellations.flatMap((c) =>
                  c.lines.map((line, i) => (
                    <polyline
                      key={`${c.id}-${i}`}
                      fill="none"
                      stroke="rgba(125,211,199,0.75)"
                      strokeWidth={lineWidth}
                      vectorEffect="non-scaling-stroke"
                      points={line.map((p) => `${p.x},${p.y}`).join(" ")}
                    />
                  )),
                )
              : null}
            {cfg.asterisms
              ? visibleAsterisms.flatMap((c) =>
                  c.lines.map((line, i) => (
                    <polyline
                      key={`a-${c.id}-${i}`}
                      fill="none"
                      stroke="rgba(251,191,36,0.88)"
                      strokeWidth={Math.max(lineWidth, 1.6)}
                      strokeDasharray="4 3"
                      vectorEffect="non-scaling-stroke"
                      points={line.map((p) => `${p.x},${p.y}`).join(" ")}
                    />
                  )),
                )
              : null}
            {cfg.asterisms
              ? visibleAsterisms.map((c) =>
                  c.label ? (
                    <text
                      key={`an-${c.id}`}
                      x={c.label.x}
                      y={c.label.y}
                      fill="rgba(253,230,138,0.92)"
                      fontSize={hudFont}
                      textAnchor="middle"
                    >
                      {c.name}
                    </text>
                  ) : null,
                )
              : null}
            {cfg.constellation_names
              ? visibleConstellations.map((c) =>
                  c.label ? (
                    <text
                      key={`n-${c.id}`}
                      x={c.label.x}
                      y={c.label.y}
                      fill="rgba(200,231,255,0.85)"
                      fontSize={hudFontLg}
                      textAnchor="middle"
                    >
                      {c.name}
                    </text>
                  ) : null,
                )
              : null}
            {cfg.star_names
              ? namedStars.map((s) => (
                  <text
                    key={s.name}
                    x={s.x + 0.012}
                    y={s.y + 0.004}
                    fill="#f3c16b"
                    fontSize={hudFontLg}
                  >
                    {s.name}
                  </text>
                ))
              : null}
            {cfg.planets && sky.sun.visible ? (
              <g>
                <circle cx={sky.sun.x} cy={sky.sun.y} r="0.012" fill="#fbbf24" />
                <text x={sky.sun.x + 0.016} y={sky.sun.y} fill="#fbbf24" fontSize={hudFontLg}>
                  Sun
                </text>
              </g>
            ) : null}
            {cfg.planets && sky.moon.visible ? (
              <g>
                <circle cx={sky.moon.x} cy={sky.moon.y} r="0.01" fill="#e8eef8" />
                <text x={sky.moon.x + 0.016} y={sky.moon.y} fill="#e8eef8" fontSize={hudFontLg}>
                  Moon
                </text>
              </g>
            ) : null}
            </g>
          </svg>
        </div>
      ) : null}
      {sky && (cfg.satellites || cfg.aircraft) ? (
        <div className="absolute inset-0 z-[3]">
          {cfg.satellites ? (
            <SatLayer
              ref={satLayerRef}
              samples={sats}
              dt={satDt}
              iconScale={cfg.sat_icon_scale}
              kinds={satKinds}
              selectedId={selectedSat}
              onSelect={(id) => {
                setSelectedSat(id);
                if (id) setSelectedAc(null);
              }}
              onPan={shiftPan}
              onPanEnd={endPan}
              view={overlayView}
              liveView={overlayViewRef}
              interactive={!cfg.aircraft}
            />
          ) : null}
          {cfg.aircraft ? (
            <AcLayer
              samples={planes}
              dt={acDt}
              iconScale={cfg.sat_icon_scale}
              selectedId={selectedAc}
              onSelect={(id) => {
                setSelectedAc(id);
                if (id) setSelectedSat(null);
              }}
              onMiss={(x, y) => {
                if (cfg.satellites) satLayerRef.current?.hitAt(x, y);
              }}
              onPan={shiftPan}
              onPanEnd={endPan}
              view={overlayView}
              liveView={overlayViewRef}
              gps={trackGps}
              ssr={trackSsr}
              psr={trackPsr}
              flightMode={flightMode}
            />
          ) : null}
        </div>
      ) : (
        <div
          className="absolute inset-0 z-[3] cursor-grab touch-none active:cursor-grabbing"
          onPointerDown={onGrabPointerDown}
        />
      )}
      <SkyToolbar
        cfg={cfg}
        panel={panel}
        onPanel={setPanel}
        zoom={zoom}
        fullscreen={fullscreen}
        satCount={filteredSats.length}
        acCount={planes.length}
        starCount={overlayStars.length}
        tleCount={sky?.tle_count}
        satKinds={satKinds}
        kindCounts={kindCounts}
        satsTotal={sats.length}
        nowList={nowList}
        selectedSat={selectedSat}
        passes={sky?.passes ?? []}
        status={status}
        onToggleLayer={(key) => void patchSky({ [key]: !cfg[key] })}
        onSatKinds={setSatKinds}
        onSelectSat={setSelectedSat}
        onPatch={patchSky}
        onCommitSlider={commitSlider}
        onZoomIn={() => zoomBy(wheelFactor(zoomRef.current, true))}
        onZoomOut={() => zoomBy(wheelFactor(zoomRef.current, false))}
        onCenterView={centerView}
        onFitView={resetView}
        onFullscreen={() => void toggleFullscreen()}
        trackGps={trackGps}
        trackSsr={trackSsr}
        trackPsr={trackPsr}
        flightMode={flightMode}
        onTrackGps={setTrackGps}
        onTrackSsr={setTrackSsr}
        onTrackPsr={setTrackPsr}
        onFlightMode={setFlightMode}
      />
      {pickedAc ? (
        <AcInspector
          ac={pickedAc}
          meta={acMeta}
          loading={acMetaLoading}
          onClose={() => setSelectedAc(null)}
        />
      ) : pickedSat ? (
        <SatInspector
          sat={pickedSat}
          satcat={satcat}
          loading={satcatLoading}
          onClose={() => setSelectedSat(null)}
        />
      ) : null}
      {tel.error || sky?.error || sky?.needs_location || acError ? (
        <p className="pointer-events-none absolute right-3 bottom-3 z-10 max-w-sm rounded-xl bg-slate-950/80 px-3 py-2 text-xs text-amber-200/90">
          {sky?.needs_location ? "Set latitude and longitude in Settings. " : ""}
          {tel.error ?? ""}
          {sky?.error ? ` ${sky.error}` : ""}
          {acError ? ` ${acError}` : ""}
        </p>
      ) : null}
    </div>
  );
}

function magVisible(mag: number | undefined, limit: number) {
  return limit > 0 && (mag ?? 99) <= limit;
}

function filterFigures(figures: Constellation[], magLimit: number): Constellation[] {
  if (magLimit <= 0) return [];
  const out: Constellation[] = [];
  for (const fig of figures) {
    const lines = fig.lines.flatMap((line) => splitByMag(line, magLimit));
    if (!lines.length) continue;
    out.push({ ...fig, lines });
  }
  return out;
}

function splitByMag(line: Pt[], magLimit: number): Pt[][] {
  const runs: Pt[][] = [];
  let run: Pt[] = [];
  for (const pt of line) {
    if (magVisible(pt.mag, magLimit)) {
      run.push(pt);
    } else {
      if (run.length >= 2) runs.push(run);
      run = [];
    }
  }
  if (run.length >= 2) runs.push(run);
  return runs;
}

function wheelFactor(zoom: number, inward: boolean) {
  const step = zoom >= 64 ? 1.5 : zoom >= 16 ? 1.32 : zoom >= 8 ? 1.25 : 1.12;
  return inward ? step : 1 / step;
}

function starRadius(mag: number) {
  return Math.max(0.00115, 0.0054 * Math.pow(10, -0.13 * Math.max(mag, -1.4)));
}

function gridDegreeLabel(g: {
  kind: string;
  alt?: number;
  az?: number;
  points: Pt[];
  label?: Pt;
}) {
  if (g.kind === "alt" || g.kind === "zenith") {
    if (g.alt == null) return null;
    const pt = g.label ?? (g.points.length ? g.points.reduce((a, b) => (b.x - b.y > a.x - a.y ? b : a)) : null);
    if (!pt) return null;
    return { x: pt.x, y: pt.y, text: `${g.alt.toFixed(0)}°` };
  }
  if (g.kind === "az" && g.az != null && g.points.length) {
    const i = Math.min(2, g.points.length - 1);
    const pt = g.points[i];
    const cardinal = ({ 0: "N", 90: "E", 180: "S", 270: "W" } as Record<number, string>)[g.az];
    return { x: pt.x, y: pt.y, text: cardinal ? `${cardinal} ${g.az}°` : `${g.az}°` };
  }
  return null;
}

