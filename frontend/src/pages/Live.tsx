import { useEffect, useRef, useState } from "react";
import LiveAdjust from "@/components/LiveAdjust";
import { formatShutter, type Telemetry } from "@/lib/utils";

const empty: Telemetry = {
  mode: "—",
  sun_alt: 0,
  exposure_us: 0,
  gain: 0,
  adu: 0,
  backend: "—",
  sensor: "",
  ts: "",
  error: null,
  capturing: false,
  session: "",
  stars: 0,
  saved: false,
  focus: false,
};

export default function Live() {
  const [image, setImage] = useState<string>("");
  const [tel, setTel] = useState<Telemetry>(empty);
  const [connected, setConnected] = useState(false);
  const [needsLocation, setNeedsLocation] = useState(false);
  const [wantFocus, setWantFocus] = useState<boolean | null>(null);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const wasFocus = useRef(false);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/ws/live`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as { image: string; telemetry: Telemetry };
      setImage(msg.image);
      setTel(msg.telemetry);
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((s: { location?: { latitude?: number; longitude?: number } }) => {
        setNeedsLocation((s.location?.latitude ?? 0) === 0 && (s.location?.longitude ?? 0) === 0);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (tel.focus && !wasFocus.current) setAdjustOpen(true);
    wasFocus.current = tel.focus;
  }, [tel.focus]);

  useEffect(() => {
    if (wantFocus === null) return;
    if (tel.focus === wantFocus) setWantFocus(null);
  }, [tel.focus, wantFocus]);

  useEffect(() => {
    if (wantFocus === null) return;
    const id = window.setTimeout(() => setWantFocus(null), 45_000);
    return () => window.clearTimeout(id);
  }, [wantFocus]);

  const switching = wantFocus !== null && tel.focus !== wantFocus;
  const shownFocus = wantFocus ?? tel.focus;

  async function toggleFocus() {
    const next = !tel.focus;
    setWantFocus(next);
    try {
      const put = await fetch("/api/settings/live", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera: { focus_mode: next } }),
      });
      if (!put.ok) throw new Error(await put.text());
    } catch {
      setWantFocus(null);
    }
  }

  const liveLabel =
    tel.camera === false ? "camera off" : connected ? "live" : "offline";
  const liveDot =
    tel.camera === false ? "bg-white/30" : connected ? "bg-aurora" : "bg-red-400";

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <section className="frame-glow relative overflow-hidden rounded-3xl bg-black">
        {image ? (
          <img src={image} alt="Live all-sky" className="block w-full bg-black object-contain" />
        ) : (
          <div className="flex aspect-4/3 items-center justify-center text-white/40">
            Waiting for first frame…
          </div>
        )}
        <button
          type="button"
          onClick={() => setAdjustOpen((v) => !v)}
          className="absolute top-4 right-4 z-20 rounded-full bg-black/55 px-4 py-2 text-sm text-ice backdrop-blur-sm hover:bg-black/70"
        >
          {adjustOpen ? "Hide adjust" : "Adjust"}
        </button>
        <LiveAdjust
          open={adjustOpen}
          onClose={() => setAdjustOpen(false)}
          mode={tel.mode}
          focus={tel.focus}
          liveExposureUs={tel.exposure_us}
          liveGain={tel.gain}
        />
      </section>
      <aside className="flex flex-col gap-4">
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Now</p>
              <p className="display mt-2 text-4xl capitalize text-ice">{tel.mode}</p>
              <p className="mt-1 text-sm text-white/55">
                Sun {tel.sun_alt >= 0 ? "+" : ""}
                {tel.sun_alt.toFixed(1)}°
              </p>
            </div>
            <span className="mt-1 inline-flex items-center gap-2 rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-white/55">
              <span className={`h-1.5 w-1.5 rounded-full ${liveDot}`} />
              {liveLabel}
            </span>
          </div>
          {tel.error ? <p className="mt-3 text-sm text-amber-300">{tel.error}</p> : null}
          {needsLocation ? (
            <p className="mt-3 text-sm text-amber-200/90">
              Set latitude and longitude in Settings so day/night match this site.
            </p>
          ) : null}
          <div className="mt-5 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm text-white/85">Focus</p>
              <p className="mt-0.5 flex items-center gap-2 text-xs text-white/40">
                {switching ? (
                  <>
                    <span className="focus-spin h-3 w-3 rounded-full border-2 border-current border-t-transparent" />
                    {wantFocus ? "Switching to focus…" : "Switching to RAW…"}
                  </>
                ) : tel.focus ? (
                  "JPEG preview"
                ) : (
                  "12-bit DNG"
                )}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={shownFocus}
              aria-label={shownFocus ? "Focus on" : "RAW capture"}
              disabled={switching}
              onClick={() => void toggleFocus()}
              className={`relative h-7 w-12 shrink-0 rounded-full transition-colors duration-200 ${
                shownFocus ? "bg-aurora" : "bg-white/15"
              } ${switching ? "animate-pulse" : ""}`}
            >
              <span
                className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform duration-200 ${
                  shownFocus ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-4 rounded-2xl border border-white/8 bg-panel/80 p-5 text-sm">
          <Stat label="Shutter" value={formatShutter(tel.exposure_us)} />
          <Stat label="Gain" value={tel.gain ? tel.gain.toFixed(2) : "—"} />
          <Stat label="Mean ADU" value={tel.adu ? tel.adu.toFixed(3) : "—"} />
          <Stat label="Stars" value={tel.stars ? String(tel.stars) : "—"} />
        </dl>
        {tel.session ? (
          <p className="px-1 text-xs text-white/35">
            {tel.session}
            {tel.saved ? " · archived" : ""}
          </p>
        ) : null}
      </aside>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-[0.18em] text-white/35">{label}</dt>
      <dd className="mt-1 font-medium text-white/90">{value}</dd>
    </div>
  );
}
