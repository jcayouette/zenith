import { useEffect, useRef, useState } from "react";
import { formatShutter } from "@/lib/utils";

type Picamera = {
  awb_enable_day: boolean;
  colour_gain_r: number;
  colour_gain_g: number;
  colour_gain_b: number;
  contrast: number;
  saturation: number;
  sharpness: number;
};

type Profile = {
  auto_exposure: boolean;
  exposure_us: number;
  max_exposure_us: number;
  gain: number;
  max_gain: number;
  target_mean: number;
};

type LiveSettings = {
  camera: { focus_mode: boolean; binning: 1 | 2 };
  picamera2: Picamera;
  day: Profile;
  night: Profile;
  [key: string]: unknown;
};

type ShutterRange = { id: string; label: string; min: number; max: number };
type BinMode = { value: number; width: number; height: number; label: string };
type Caps = {
  exposure_us: { min: number; max: number };
  analogue_gain: { min: number; max: number };
  binning: BinMode[];
  shutter_ranges: ShutterRange[];
};

const FALLBACK_CAPS: Caps = {
  exposure_us: { min: 100, max: 120_000_000 },
  analogue_gain: { min: 1, max: 22 },
  binning: [
    { value: 1, width: 4056, height: 3040, label: "1× · 4056×3040" },
    { value: 2, width: 2028, height: 1520, label: "2× · 2028×1520" },
  ],
  shutter_ranges: [
    { id: "0.1-1ms", label: "0.1 – 1 ms", min: 100, max: 1_000 },
    { id: "1-10ms", label: "1 – 10 ms", min: 1_000, max: 10_000 },
    { id: "10-100ms", label: "10 – 100 ms", min: 10_000, max: 100_000 },
    { id: "0.1-1s", label: "0.1 – 1 s", min: 100_000, max: 1_000_000 },
    { id: "1-10s", label: "1 – 10 s", min: 1_000_000, max: 10_000_000 },
    { id: "10-60s", label: "10 – 60 s", min: 10_000_000, max: 60_000_000 },
    { id: "60-120s", label: "60 – 120 s", min: 60_000_000, max: 120_000_000 },
  ],
};

type ProfileKey = "day" | "night";

export default function LiveAdjust({
  open,
  onClose,
  mode,
  focus,
  liveExposureUs,
  liveGain,
}: {
  open: boolean;
  onClose: () => void;
  mode: string;
  focus: boolean;
  liveExposureUs: number;
  liveGain: number;
}) {
  const [settings, setSettings] = useState<LiveSettings | null>(null);
  const [caps, setCaps] = useState<Caps>(FALLBACK_CAPS);
  const [rangeId, setRangeId] = useState("10-100ms");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const timer = useRef<number>(0);
  const pending = useRef<Record<string, unknown>>({});

  const profileKey: ProfileKey = mode === "night" ? "night" : "day";

  useEffect(() => {
    if (!open) return;
    void fetch("/api/camera/caps")
      .then((r) => r.json())
      .then((c: Caps) => setCaps(c))
      .catch(() => undefined);
    fetch("/api/settings")
      .then((r) => r.json())
      .then((s: LiveSettings) => {
        setSettings(s);
        setDirty(false);
        setStatus(null);
        const us = s[profileKey]?.exposure_us ?? 33_333;
        setRangeId(rangeFor(us, FALLBACK_CAPS.shutter_ranges).id);
      })
      .catch(() => undefined);
  }, [open, profileKey]);

  function queuePatch(partial: Record<string, unknown>) {
    pending.current = deepMerge(pending.current, partial);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const body = pending.current;
      pending.current = {};
      void fetch("/api/settings/live", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }, 80);
  }

  function setPicamera(field: keyof Picamera, value: number) {
    if (!settings) return;
    const picamera2 = { ...settings.picamera2, [field]: value };
    setSettings({ ...settings, picamera2 });
    setDirty(true);
    queuePatch({ picamera2: { [field]: value } });
  }

  function setProfile(field: keyof Profile, value: boolean | number, extra?: Partial<Profile>) {
    if (!settings) return;
    const current = { ...settings[profileKey], [field]: value, ...extra } as Profile;
    if (field === "gain" || field === "exposure_us") current.auto_exposure = false;
    setSettings({ ...settings, [profileKey]: current });
    setDirty(true);
    const patch: Partial<Profile> = { [field]: value, ...extra } as Partial<Profile>;
    if (field === "gain" || field === "exposure_us") patch.auto_exposure = false;
    queuePatch({ [profileKey]: patch });
  }

  function setShutter(us: number, range: ShutterRange) {
    const capped = Math.round(Math.min(Math.max(us, range.min), range.max));
    setProfile("exposure_us", capped);
  }

  function setBinning(value: 1 | 2) {
    if (!settings) return;
    const camera = { ...settings.camera, binning: value };
    setSettings({ ...settings, camera });
    setDirty(true);
    queuePatch({ camera: { binning: value } });
  }

  async function save() {
    setSaving(true);
    try {
      const res = await fetch("/api/settings/commit", { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      setDirty(false);
      setStatus("Saved to config.yaml");
    } catch {
      setStatus("Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!open || !settings) return null;
  const profile = settings[profileKey];
  const range = caps.shutter_ranges.find((r) => r.id === rangeId) ?? rangeFor(profile.exposure_us, caps.shutter_ranges);
  const expValue = profile.auto_exposure ? liveExposureUs || profile.exposure_us : profile.exposure_us;
  const gainValue = profile.auto_exposure ? liveGain || profile.gain : profile.gain;
  const gainMax = Math.min(profile.max_gain || caps.analogue_gain.max, caps.analogue_gain.max);

  return (
    <div className="absolute inset-y-0 right-0 z-10 flex w-[min(100%,21rem)] flex-col border-l border-white/10 bg-[#070b14]/92 backdrop-blur-md">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Adjust</p>
          <p className="text-sm text-white/70">
            {profileKey === "night" ? "Night" : "Day"}
            {focus ? " · focus" : " · RAW"}
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded-full px-3 py-1 text-xs text-white/50 hover:bg-white/10">
          Close
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 pb-4">
        <label className="block">
          <span className="text-xs uppercase tracking-[0.16em] text-white/45">Binning</span>
          <select
            className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
            value={settings.camera.binning}
            onChange={(e) => setBinning(Number(e.target.value) === 2 ? 2 : 1)}
          >
            {caps.binning.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
        </label>
        <Toggle
          label="Auto exposure"
          on={profile.auto_exposure}
          onClick={() => setProfile("auto_exposure", !profile.auto_exposure)}
        />
        <Toggle
          label="Auto white balance"
          on={settings.picamera2.awb_enable_day}
          onClick={() => {
            const awb_enable_day = !settings.picamera2.awb_enable_day;
            setSettings({ ...settings, picamera2: { ...settings.picamera2, awb_enable_day } });
            setDirty(true);
            queuePatch({ picamera2: { awb_enable_day } });
          }}
        />
        <label className="block">
          <span className="text-xs uppercase tracking-[0.16em] text-white/45">Shutter range</span>
          <select
            className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
            value={range.id}
            onChange={(e) => {
              const next = caps.shutter_ranges.find((r) => r.id === e.target.value);
              if (!next) return;
              setRangeId(next.id);
              const clamped = Math.min(Math.max(expValue, next.min), next.max);
              if (clamped !== expValue) setShutter(clamped, next);
            }}
          >
            {caps.shutter_ranges.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <Slider
          label="Shutter / exposure"
          value={usToSlider(expValue, range.min, range.max)}
          min={0}
          max={1000}
          step={1}
          format={() => formatShutter(expValue)}
          onChange={(t) => setShutter(sliderToUs(t, range.min, range.max), range)}
        />
        <Slider
          label="Auto shutter limit"
          value={usToSlider(profile.max_exposure_us, caps.exposure_us.min, caps.exposure_us.max)}
          min={0}
          max={1000}
          step={1}
          format={() => formatShutter(profile.max_exposure_us)}
          onChange={(t) =>
            setProfile("max_exposure_us", sliderToUs(t, caps.exposure_us.min, caps.exposure_us.max), {
              auto_exposure: profile.auto_exposure,
            })
          }
        />
        <Slider
          label="Brightness target"
          value={profile.target_mean}
          min={0.05}
          max={0.7}
          step={0.01}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setProfile("target_mean", v, { auto_exposure: profile.auto_exposure })}
        />
        <Slider
          label="Analogue gain"
          value={gainValue}
          min={caps.analogue_gain.min}
          max={gainMax}
          step={0.1}
          format={(v) => v.toFixed(1)}
          onChange={(v) => setProfile("gain", v)}
        />
        <Slider
          label="Red"
          value={settings.picamera2.colour_gain_r}
          min={0}
          max={8}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setPicamera("colour_gain_r", v)}
        />
        <Slider
          label="Green"
          value={settings.picamera2.colour_gain_g}
          min={0}
          max={8}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setPicamera("colour_gain_g", v)}
        />
        <Slider
          label="Blue"
          value={settings.picamera2.colour_gain_b}
          min={0}
          max={8}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setPicamera("colour_gain_b", v)}
        />
        <Slider
          label="Contrast"
          value={settings.picamera2.contrast}
          min={0}
          max={2}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setPicamera("contrast", v)}
        />
        <Slider
          label="Saturation"
          value={settings.picamera2.saturation}
          min={0}
          max={2}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setPicamera("saturation", v)}
        />
        <Slider
          label="Sharpness"
          value={settings.picamera2.sharpness}
          min={0}
          max={4}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => setPicamera("sharpness", v)}
        />
        <p className="text-[11px] leading-relaxed text-white/40">
          HQ IMX477: same shutter, gain, colour, and ISP for focus and RAW. Focus only
          skips DNG/PNG. Pick a shutter range, then slide. Save writes config.yaml.
        </p>
      </div>
      <div className="border-t border-white/8 p-4">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || !dirty}
          className="w-full rounded-full bg-ice px-4 py-2 text-sm font-medium text-ink disabled:bg-white/10 disabled:text-white/40"
        >
          {saving ? "Saving…" : dirty ? "Save settings" : "Saved"}
        </button>
        {status ? <p className="mt-2 text-center text-xs text-aurora">{status}</p> : null}
      </div>
    </div>
  );
}

function rangeFor(us: number, ranges: ShutterRange[]): ShutterRange {
  return ranges.find((r) => us >= r.min && us <= r.max) ?? ranges[2] ?? ranges[0];
}

function usToSlider(us: number, min: number, max: number) {
  const lo = Math.log(Math.max(min, 1));
  const hi = Math.log(Math.max(max, min + 1));
  return Math.round(((Math.log(Math.min(Math.max(us, min), max)) - lo) / (hi - lo)) * 1000);
}

function sliderToUs(t: number, min: number, max: number) {
  const lo = Math.log(Math.max(min, 1));
  const hi = Math.log(Math.max(max, min + 1));
  return Math.round(Math.exp(lo + (t / 1000) * (hi - lo)));
}

function deepMerge(base: Record<string, unknown>, patch: Record<string, unknown>) {
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const prev = out[key];
    if (value && typeof value === "object" && !Array.isArray(value) && prev && typeof prev === "object" && !Array.isArray(prev)) {
      out[key] = deepMerge(prev as Record<string, unknown>, value as Record<string, unknown>);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function Toggle({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-[0.16em] text-white/45">{label}</span>
      <button
        type="button"
        onClick={onClick}
        className={`rounded-full px-3 py-1 text-xs font-medium ${on ? "bg-aurora/20 text-aurora" : "bg-white/10 text-white/50"}`}
      >
        {on ? "On" : "Off"}
      </button>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <label className={`block ${disabled ? "opacity-45" : ""}`}>
      <span className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-white/45">
        {label}
        <span className="font-sans tracking-normal text-white/80">{format(value)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : min}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-aurora"
      />
    </label>
  );
}
