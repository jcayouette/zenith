import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import SatLayer, { SAT_KIND, SatIcon, satKindOf } from "@/components/SatLayer";
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

type LayerKey =
  | "constellations"
  | "constellation_names"
  | "asterisms"
  | "star_names"
  | "grid"
  | "planets"
  | "satellites";

type SkyConfig = {
  constellations: boolean;
  constellation_names: boolean;
  asterisms: boolean;
  star_names: boolean;
  grid: boolean;
  planets: boolean;
  satellites: boolean;
  mag_limit: number;
  star_name_mag: number;
  min_sat_alt_deg: number;
  sat_icon_scale: number;
  horizon: number;
  constellation_line_px: number;
  simulator_catalog: boolean;
};

type SettingsValues = { sky?: Partial<SkyConfig> };

const LAYER_LABEL: Record<LayerKey, string> = {
  constellations: "Constellations",
  constellation_names: "Names",
  asterisms: "Asterisms",
  star_names: "Bright stars",
  grid: "Alt/az grid",
  planets: "Sun & moon",
  satellites: "Satellites",
};

const SKY_DEFAULTS: SkyConfig = {
  constellations: true,
  constellation_names: true,
  asterisms: true,
  star_names: true,
  grid: false,
  planets: true,
  satellites: true,
  mag_limit: 5,
  star_name_mag: 1.85,
  min_sat_alt_deg: 0,
  sat_icon_scale: 1,
  horizon: 1,
  constellation_line_px: 1,
  simulator_catalog: true,
};

const emptyTel = { mode: "—", sun_alt: 0, backend: "—", error: null as string | null, camera: true };

export default function Sky() {
  const client = useQueryClient();
  const [image, setImage] = useState("");
  const [tel, setTel] = useState(emptyTel);
  const [sky, setSky] = useState<SkyPayload | null>(null);
  const [liveSats, setLiveSats] = useState<Pt[] | null>(null);
  const [satDt, setSatDt] = useState(1);
  const [selectedSat, setSelectedSat] = useState<string | null>(null);
  const refetchTimer = useRef(0);
  const commitTimer = useRef(0);
  const patchTimer = useRef(0);
  const patchGen = useRef(0);
  const draftRef = useRef<Partial<SkyConfig>>({});
  const reloadAfterPatch = useRef(false);
  const [draftRev, setDraftRev] = useState(0);
  const [satKinds, setSatKinds] = useState<string[] | null>(null);

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
  const overlayStars = useMemo(
    () => (sky?.stars ?? []).filter((s) => (s.mag ?? 99) <= cfg.mag_limit),
    [sky, cfg.mag_limit],
  );
  const namedStars = useMemo(
    () => (sky?.star_names ?? []).filter((s) => (s.mag ?? 99) <= cfg.star_name_mag),
    [sky, cfg.star_name_mag],
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

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <section className="frame-glow overflow-hidden rounded-3xl bg-black">
        <div className="relative">
        {image ? (
          <img src={image} alt="All-sky with catalog overlay" className="block h-auto w-full bg-black" />
        ) : (
          <div className="flex aspect-4/3 items-center justify-center text-white/40">Waiting for live frame…</div>
        )}
        {sky ? (
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
                      fontSize={alt ? "0.017" : "0.015"}
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
                      fontSize="0.016"
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
                      fontSize="0.018"
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
                    fontSize="0.016"
                  >
                    {s.name}
                  </text>
                ))
              : null}
            {cfg.planets && sky.sun.visible ? (
              <g>
                <circle cx={sky.sun.x} cy={sky.sun.y} r="0.012" fill="#fbbf24" />
                <text x={sky.sun.x + 0.016} y={sky.sun.y} fill="#fbbf24" fontSize="0.018">
                  Sun
                </text>
              </g>
            ) : null}
            {cfg.planets && sky.moon.visible ? (
              <g>
                <circle cx={sky.moon.x} cy={sky.moon.y} r="0.01" fill="#e8eef8" />
                <text x={sky.moon.x + 0.016} y={sky.moon.y} fill="#e8eef8" fontSize="0.018">
                  Moon
                </text>
              </g>
            ) : null}
            </g>
          </svg>
        ) : null}
        {sky && cfg.satellites ? (
          <SatLayer
            samples={sats}
            dt={satDt}
            fit={fit}
            iconScale={cfg.sat_icon_scale}
            kinds={satKinds}
            selectedId={selectedSat}
            onSelect={setSelectedSat}
            kindCounts={kindCounts}
          />
        ) : null}
        </div>
      </section>
      <aside className="flex flex-col gap-4">
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Sky</p>
          <p className="display mt-2 text-3xl text-ice">Catalog overlay</p>
          <p className="mt-2 text-sm text-white/55">
            Overlay radius is the fit knob for now. After a real night we can lock it to a star
            match. Mag limit shows and hides catalog stars, including constellation vertices.
          </p>
          <p className="mt-2 text-xs text-white/40">
            {tel.backend} · {tel.mode}
            {Number.isFinite(tel.sun_alt) ? ` · sun ${tel.sun_alt >= 0 ? "+" : ""}${tel.sun_alt.toFixed(1)}°` : ""}
            {` · ${overlayStars.length} stars ≤ ${cfg.mag_limit.toFixed(1)}`}
            {cfg.satellites ? ` · ${filteredSats.length} sat` : ""}
            {sky?.tle_count ? ` · ${sky.tle_count} TLE` : ""}
          </p>
          {tel.error ? <p className="mt-2 text-sm text-amber-300">{tel.error}</p> : null}
          {sky?.needs_location ? (
            <p className="mt-3 text-sm text-amber-200/90">Set latitude and longitude in Settings.</p>
          ) : null}
          {sky?.error ? <p className="mt-3 text-sm text-amber-200/90">{sky.error}</p> : null}
        </div>
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Layers</p>
          <ul className="mt-3 space-y-2">
            {(Object.keys(LAYER_LABEL) as LayerKey[]).map((key) => (
              <li key={key} className="flex items-center justify-between gap-3">
                <span className="text-sm text-white/80">{LAYER_LABEL[key]}</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={cfg[key]}
                  onClick={() => void patchSky({ [key]: !cfg[key] })}
                  className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${
                    cfg[key] ? "bg-aurora" : "bg-white/15"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                      cfg[key] ? "translate-x-4" : "translate-x-0"
                    }`}
                  />
                </button>
              </li>
            ))}
          </ul>
        </div>
        {cfg.satellites ? (
          <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
            <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Satellite types</p>
            <div className="mt-3 flex flex-col gap-2">
              <button
                type="button"
                aria-pressed={satKinds === null}
                onClick={() => setSatKinds(null)}
                className={`rounded-lg px-3 py-1.5 text-left text-xs font-medium transition-colors ${
                  satKinds === null
                    ? "bg-aurora/90 text-slate-950"
                    : "bg-white/8 text-white/70 hover:bg-white/12"
                }`}
              >
                All types
                <span className="ml-2 text-[10px] opacity-70">{sats.length}</span>
              </button>
              <ul className="grid grid-cols-2 gap-2">
                {Object.entries(SAT_KIND).map(([id, meta]) => {
                  const on = satKinds === null || satKinds.includes(id);
                  const isolated = satKinds?.length === 1 && satKinds[0] === id;
                  const count = kindCounts[id] ?? 0;
                  return (
                    <li key={id}>
                      <button
                        type="button"
                        aria-pressed={satKinds !== null && satKinds.includes(id)}
                        onClick={() => {
                          if (satKinds === null) {
                            setSatKinds([id]);
                            return;
                          }
                          const next = satKinds.includes(id)
                            ? satKinds.filter((k) => k !== id)
                            : [...satKinds, id];
                          setSatKinds(next.length === 0 || next.length === Object.keys(SAT_KIND).length ? null : next);
                        }}
                        className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                          on ? "bg-white/10 text-white/90" : "text-white/35 hover:bg-white/6 hover:text-white/55"
                        } ${isolated ? "ring-1 ring-white/25" : ""}`}
                      >
                        <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center" style={{ opacity: on ? 1 : 0.35 }}>
                          <SatIcon color={meta.color} />
                        </span>
                        <span className="min-w-0 flex-1 truncate">{meta.label}</span>
                        <span className="tabular-nums text-[10px] text-white/40">{count}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        ) : null}
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Fit</p>
          <div className="mt-3 space-y-4">
            <Slider
              label="Overlay radius"
              hint="Shrink until the stick figures sit inside the lens circle."
              value={cfg.horizon}
              min={0.4}
              max={1.5}
              step={0.01}
              format={(v) => v.toFixed(2)}
              onChange={(v) => patchSky({ horizon: v })}
              onCommit={commitSlider}
            />
            <Slider
              label="Line thickness"
              value={cfg.constellation_line_px}
              min={0.5}
              max={6}
              step={0.5}
              format={(v) => `${v.toFixed(1)} px`}
              onChange={(v) => patchSky({ constellation_line_px: v })}
              onCommit={commitSlider}
            />
            <Slider
              label="Star name mag"
              hint="Label named stars at or brighter than this (lower = fewer names)."
              value={cfg.star_name_mag}
              min={0}
              max={6}
              step={0.05}
              format={(v) => v.toFixed(2)}
              onChange={(v) => patchSky({ star_name_mag: v })}
              onCommit={commitSlider}
            />
            <Slider
              label="Mag limit"
              hint="Faintest overlay stars and constellation vertices. 5 is a dark-site sky."
              value={cfg.mag_limit}
              min={1}
              max={6}
              step={0.1}
              format={(v) => v.toFixed(1)}
              onChange={(v) => patchSky({ mag_limit: v })}
              onCommit={commitSlider}
            />
            <Slider
              label="Satellite icon size"
              value={cfg.sat_icon_scale}
              min={0.4}
              max={4}
              step={0.1}
              format={(v) => `${v.toFixed(1)}×`}
              onChange={(v) => patchSky({ sat_icon_scale: v })}
              onCommit={commitSlider}
            />
            <Slider
              label="Min sat altitude"
              hint="0° is Stellarium-style: every catalog object above the horizon. Raise it to hide the crowded limb."
              value={cfg.min_sat_alt_deg}
              min={0}
              max={70}
              step={1}
              format={(v) => `${v.toFixed(0)}°`}
              onChange={(v) => patchSky({ min_sat_alt_deg: v }, true)}
              onCommit={commitSlider}
            />
          </div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Now</p>
          {cfg.satellites && filteredSats.length ? (
            <ul className="mt-3 space-y-2 text-sm">
              {nowList.map((s) => {
                const color = SAT_KIND[s.kind && SAT_KIND[s.kind] ? s.kind : "other"].color;
                return (
                <li key={s.norad || s.name}>
                  <button
                    type="button"
                    className={`flex w-full items-baseline justify-between gap-3 rounded-lg px-1 py-0.5 text-left ${
                      selectedSat === (s.norad || s.name) ? "bg-white/10" : "hover:bg-white/5"
                    }`}
                    onClick={() => setSelectedSat(s.norad || s.name || null)}
                  >
                    <span className="font-medium" style={{ color }}>
                      {s.name}
                    </span>
                    <span className="text-xs text-white/45">
                      {s.kind && SAT_KIND[s.kind] ? `${SAT_KIND[s.kind].label} · ` : ""}
                      {s.alt != null ? `${s.alt.toFixed(0)}°` : ""}
                      {s.az != null ? ` · az ${s.az.toFixed(0)}°` : ""}
                    </span>
                  </button>
                </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-white/45">
              {cfg.satellites
                ? satKinds
                  ? "No satellites of the selected types above the altitude cut."
                  : `None above ${cfg.min_sat_alt_deg.toFixed(0)}° right now. ISS and Hubble still show in the 24 h list when a pass is due.`
                : "Satellite layer is off."}
            </p>
          )}
        </div>
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Passes (24 h)</p>
          {sky?.passes?.length ? (
            <ul className="mt-3 space-y-3 text-sm">
              {sky.passes.map((p) => (
                <li key={`${p.name}-${p.start}`}>
                  <p className="text-white/90">{p.name}</p>
                  <p className="text-xs text-white/45">
                    {fmtPass(p.start)} → {fmtPass(p.end)} · max {p.max_alt.toFixed(0)}°
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-white/45">
              No ISS / CSS / Hubble passes above the altitude cut in the next 24 hours.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

function filterFigures(figures: Constellation[], magLimit: number): Constellation[] {
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
    if ((pt.mag ?? 99) <= magLimit) {
      run.push(pt);
    } else {
      if (run.length >= 2) runs.push(run);
      run = [];
    }
  }
  if (run.length >= 2) runs.push(run);
  return runs;
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

function Slider({
  label,
  hint,
  value,
  min,
  max,
  step,
  format,
  onChange,
  onCommit,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
  onCommit?: () => void;
}) {
  return (
    <label className="block">
      <span className="flex items-center justify-between text-sm text-white/80">
        {label}
        <span className="text-xs text-white/45">{format(value)}</span>
      </span>
      {hint ? <span className="mt-0.5 block text-xs text-white/35">{hint}</span> : null}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerUp={onCommit}
        onKeyUp={onCommit}
        className="mt-2 w-full accent-aurora"
      />
    </label>
  );
}

function fmtPass(iso: string) {
  const t = iso.replace("T", " ");
  return t.slice(0, 16);
}
