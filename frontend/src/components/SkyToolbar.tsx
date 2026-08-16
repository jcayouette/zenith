import type { ReactNode } from "react";
import { SAT_KIND, SatIcon } from "@/components/SatLayer";

export type LayerKey =
  | "constellations"
  | "constellation_names"
  | "asterisms"
  | "star_names"
  | "grid"
  | "planets"
  | "satellites"
  | "aircraft";

export type SkyConfig = {
  constellations: boolean;
  constellation_names: boolean;
  asterisms: boolean;
  star_names: boolean;
  grid: boolean;
  planets: boolean;
  satellites: boolean;
  aircraft: boolean;
  mag_limit: number;
  star_name_mag: number;
  min_sat_alt_deg: number;
  sat_icon_scale: number;
  horizon: number;
  constellation_line_px: number;
  simulator_catalog: boolean;
};

type Pass = {
  name: string;
  start: string;
  peak: string;
  end: string;
  max_alt: number;
};

type NowSat = {
  name?: string;
  norad?: string;
  kind?: string;
  alt?: number;
  az?: number;
};

export type PanelId = "layers" | "types" | "fit" | "now";

const LAYER_LABEL: Record<LayerKey, string> = {
  constellations: "Constellations",
  constellation_names: "Names",
  asterisms: "Asterisms",
  star_names: "Bright stars",
  grid: "Alt/az grid",
  planets: "Sun & moon",
  satellites: "Satellites",
  aircraft: "Aircraft",
};

type Props = {
  cfg: SkyConfig;
  panel: PanelId | null;
  onPanel: (id: PanelId | null) => void;
  zoom: number;
  fullscreen: boolean;
  satCount: number;
  acCount?: number;
  starCount: number;
  tleCount?: number;
  satKinds: string[] | null;
  kindCounts: Record<string, number>;
  satsTotal: number;
  nowList: NowSat[];
  selectedSat: string | null;
  passes: Pass[];
  status: string;
  onToggleLayer: (key: LayerKey) => void;
  onSatKinds: (next: string[] | null) => void;
  onSelectSat: (id: string | null) => void;
  onPatch: (partial: Partial<SkyConfig>, reload?: boolean) => void;
  onCommitSlider: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
  onFullscreen: () => void;
};

export default function SkyToolbar(props: Props) {
  const {
    cfg,
    panel,
    onPanel,
    zoom,
    fullscreen,
    satCount,
    acCount = 0,
    starCount,
    tleCount,
    satKinds,
    kindCounts,
    satsTotal,
    nowList,
    selectedSat,
    passes,
    status,
    onToggleLayer,
    onSatKinds,
    onSelectSat,
    onPatch,
    onCommitSlider,
    onZoomIn,
    onZoomOut,
    onResetView,
    onFullscreen,
  } = props;

  function toggle(id: PanelId) {
    onPanel(panel === id ? null : id);
  }

  return (
    <div
      className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-3"
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div className="pointer-events-auto flex max-w-[min(100%,28rem)] flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-white/12 bg-slate-950/80 p-1.5 shadow-lg backdrop-blur-md">
          <ToolBtn active={panel === "layers"} onClick={() => toggle("layers")}>
            Layers
          </ToolBtn>
          <ToolBtn active={panel === "types"} onClick={() => toggle("types")} disabled={!cfg.satellites}>
            Types
            <span className="ml-1 tabular-nums text-[10px] opacity-70">{satCount}</span>
          </ToolBtn>
          <ToolBtn active={panel === "fit"} onClick={() => toggle("fit")}>
            Fit
          </ToolBtn>
          <ToolBtn active={panel === "now"} onClick={() => toggle("now")}>
            Now
          </ToolBtn>
        </div>
        {panel === "layers" ? (
          <Panel title="Layers">
            <ul className="space-y-2">
              {(Object.keys(LAYER_LABEL) as LayerKey[]).map((key) => (
                <li key={key} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-white/80">{LAYER_LABEL[key]}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={cfg[key]}
                    onClick={() => onToggleLayer(key)}
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
          </Panel>
        ) : null}
        {panel === "types" && cfg.satellites ? (
          <Panel title="Satellite types">
            <button
              type="button"
              aria-pressed={satKinds === null}
              onClick={() => onSatKinds(null)}
              className={`w-full rounded-lg px-3 py-1.5 text-left text-xs font-medium transition-colors ${
                satKinds === null ? "bg-aurora/90 text-slate-950" : "bg-white/8 text-white/70 hover:bg-white/12"
              }`}
            >
              All types
              <span className="ml-2 text-[10px] opacity-70">{satsTotal}</span>
            </button>
            <ul className="mt-2 grid grid-cols-2 gap-2">
              {Object.entries(SAT_KIND).map(([id, meta]) => {
                const on = satKinds === null || satKinds.includes(id);
                const isolated = satKinds?.length === 1 && satKinds[0] === id;
                return (
                  <li key={id}>
                    <button
                      type="button"
                      aria-pressed={satKinds !== null && satKinds.includes(id)}
                      onClick={() => {
                        if (satKinds === null) {
                          onSatKinds([id]);
                          return;
                        }
                        const next = satKinds.includes(id)
                          ? satKinds.filter((k) => k !== id)
                          : [...satKinds, id];
                        onSatKinds(
                          next.length === 0 || next.length === Object.keys(SAT_KIND).length ? null : next,
                        );
                      }}
                      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                        on ? "bg-white/10 text-white/90" : "text-white/35 hover:bg-white/6 hover:text-white/55"
                      } ${isolated ? "ring-1 ring-white/25" : ""}`}
                    >
                      <span
                        className="inline-flex h-4 w-4 shrink-0 items-center justify-center"
                        style={{ opacity: on ? 1 : 0.35 }}
                      >
                        <SatIcon color={meta.color} />
                      </span>
                      <span className="min-w-0 flex-1 truncate">{meta.label}</span>
                      <span className="tabular-nums text-[10px] text-white/40">{kindCounts[id] ?? 0}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Panel>
        ) : null}
        {panel === "fit" ? (
          <Panel title="Fit & overlay">
            <div
              className="space-y-4"
              onWheel={(e) => e.stopPropagation()}
            >
              <Slider
                label="Overlay radius"
                hint="Shrink until the stick figures sit inside the lens circle."
                value={cfg.horizon}
                min={0.4}
                max={1.5}
                step={0.01}
                format={(v) => v.toFixed(2)}
                onChange={(v) => onPatch({ horizon: v })}
                onCommit={onCommitSlider}
              />
              <Slider
                label="Line thickness"
                value={cfg.constellation_line_px}
                min={0.5}
                max={6}
                step={0.5}
                format={(v) => `${v.toFixed(1)} px`}
                onChange={(v) => onPatch({ constellation_line_px: v })}
                onCommit={onCommitSlider}
              />
              <Slider
                label="Star name mag"
                hint="Label named stars at or brighter than this (lower = fewer names)."
                value={cfg.star_name_mag}
                min={0}
                max={6}
                step={0.05}
                format={(v) => v.toFixed(2)}
                onChange={(v) => onPatch({ star_name_mag: v })}
                onCommit={onCommitSlider}
              />
              <Slider
                label="Mag limit"
                hint="Faintest overlay stars and constellation vertices. 5 is a dark-site sky."
                value={cfg.mag_limit}
                min={1}
                max={6}
                step={0.1}
                format={(v) => v.toFixed(1)}
                onChange={(v) => onPatch({ mag_limit: v })}
                onCommit={onCommitSlider}
              />
              <Slider
                label="Satellite icon size"
                value={cfg.sat_icon_scale}
                min={0.4}
                max={4}
                step={0.1}
                format={(v) => `${v.toFixed(1)}×`}
                onChange={(v) => onPatch({ sat_icon_scale: v })}
                onCommit={onCommitSlider}
              />
              <Slider
                label="Min sat altitude"
                hint="0° shows everything above the horizon."
                value={cfg.min_sat_alt_deg}
                min={0}
                max={70}
                step={1}
                format={(v) => `${v.toFixed(0)}°`}
                onChange={(v) => onPatch({ min_sat_alt_deg: v }, true)}
                onCommit={onCommitSlider}
              />
            </div>
          </Panel>
        ) : null}
        {panel === "now" ? (
          <Panel title="Now & passes">
            {cfg.satellites && nowList.length ? (
              <ul className="space-y-1 text-sm">
                {nowList.map((s) => {
                  const color = SAT_KIND[s.kind && SAT_KIND[s.kind] ? s.kind : "other"].color;
                  const id = s.norad || s.name || "";
                  return (
                    <li key={id}>
                      <button
                        type="button"
                        className={`flex w-full items-baseline justify-between gap-3 rounded-lg px-1 py-0.5 text-left ${
                          selectedSat === id ? "bg-white/10" : "hover:bg-white/5"
                        }`}
                        onClick={() => onSelectSat(id || null)}
                      >
                        <span className="font-medium" style={{ color }}>
                          {s.name}
                        </span>
                        <span className="text-xs text-white/45">
                          {s.kind && SAT_KIND[s.kind] ? `${SAT_KIND[s.kind].label} · ` : ""}
                          {s.alt != null ? `${s.alt.toFixed(0)}°` : ""}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-white/45">
                {cfg.satellites ? "No satellites above the altitude cut." : "Satellite layer is off."}
              </p>
            )}
            <p className="mt-4 text-[10px] uppercase tracking-[0.18em] text-white/35">Passes (24 h)</p>
            {passes.length ? (
              <ul className="mt-2 space-y-2 text-sm">
                {passes.map((p) => (
                  <li key={`${p.name}-${p.start}`}>
                    <p className="text-white/90">{p.name}</p>
                    <p className="text-xs text-white/45">
                      {fmtPass(p.start)} → {fmtPass(p.end)} · max {p.max_alt.toFixed(0)}°
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-white/45">No ISS / CSS / Hubble passes in the next 24 hours.</p>
            )}
          </Panel>
        ) : null}
      </div>
      <div className="pointer-events-auto flex flex-col items-end gap-2">
        <div className="flex items-center gap-1 rounded-2xl border border-white/12 bg-slate-950/80 p-1.5 shadow-lg backdrop-blur-md">
          <IconBtn label="Zoom out" onClick={onZoomOut}>
            −
          </IconBtn>
          <button
            type="button"
            onClick={onResetView}
            className="min-w-[3.25rem] rounded-xl px-2 py-1.5 text-xs tabular-nums text-white/80 hover:bg-white/10"
            title="Reset view"
          >
            {Math.round(zoom * 100)}%
          </button>
          <IconBtn label="Zoom in" onClick={onZoomIn}>
            +
          </IconBtn>
          <IconBtn label={fullscreen ? "Exit fullscreen" : "Fullscreen"} onClick={onFullscreen}>
            {fullscreen ? "✕" : "⛶"}
          </IconBtn>
        </div>
        <p className="max-w-[16rem] rounded-xl bg-slate-950/55 px-2.5 py-1 text-right text-[10px] leading-snug text-white/50 backdrop-blur-sm">
          {status}
          {` · ${starCount} stars`}
          {cfg.satellites ? ` · ${satCount} sat` : ""}
          {cfg.aircraft ? ` · ${acCount} ac` : ""}
          {tleCount ? ` · ${tleCount} TLE` : ""}
        </p>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="max-h-[min(70vh,32rem)] overflow-y-auto rounded-2xl border border-white/12 bg-slate-950/92 p-4 shadow-xl backdrop-blur-md">
      <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">{title}</p>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function ToolBtn({
  active,
  disabled,
  onClick,
  children,
}: {
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-xl px-3 py-1.5 text-xs font-medium transition ${
        disabled
          ? "text-white/25"
          : active
            ? "bg-aurora/90 text-slate-950"
            : "text-white/80 hover:bg-white/10"
      }`}
    >
      {children}
    </button>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-8 w-8 items-center justify-center rounded-xl text-sm text-white/80 hover:bg-white/10"
    >
      {children}
    </button>
  );
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
