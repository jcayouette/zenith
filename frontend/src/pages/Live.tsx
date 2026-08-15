import { useEffect, useState } from "react";
import { formatExposure, type Telemetry } from "@/lib/utils";

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
};

export default function Live() {
  const [image, setImage] = useState<string>("");
  const [tel, setTel] = useState<Telemetry>(empty);
  const [connected, setConnected] = useState(false);

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

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <section className="frame-glow overflow-hidden rounded-3xl bg-black">
        {image ? (
          <img src={image} alt="Live all-sky" className="block w-full bg-black object-contain" />
        ) : (
          <div className="flex aspect-4/3 items-center justify-center text-white/40">
            Waiting for first frame…
          </div>
        )}
      </section>
      <aside className="flex flex-col gap-4">
        <div className="rounded-2xl border border-white/8 bg-panel/80 p-5">
          <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Now</p>
          <p className="mt-2 font-serif text-4xl capitalize text-ice">{tel.mode}</p>
          <p className="mt-1 text-sm text-white/55">
            Sun {tel.sun_alt >= 0 ? "+" : ""}
            {tel.sun_alt.toFixed(1)}°
          </p>
          <div className="mt-4 flex items-center gap-2 text-xs">
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-aurora" : "bg-red-400"}`} />
            {connected ? "live websocket" : "disconnected"}
            {tel.capturing ? " · capturing" : ""}
          </div>
          {tel.error ? <p className="mt-3 text-sm text-amber-300">{tel.error}</p> : null}
        </div>
        <dl className="grid grid-cols-2 gap-3 rounded-2xl border border-white/8 bg-panel/80 p-5 text-sm">
          <Stat label="Exposure" value={formatExposure(tel.exposure_us)} />
          <Stat label="Gain" value={tel.gain ? tel.gain.toFixed(2) : "—"} />
          <Stat label="Mean ADU" value={tel.adu ? tel.adu.toFixed(3) : "—"} />
          <Stat label="Backend" value={tel.backend} />
          <Stat label="Stamp" value={tel.ts || "—"} wide />
        </dl>
        <p className="px-1 text-xs leading-relaxed text-white/40">
          Simulator draws a rotating star field until Picamera2 is selected on the Pi. Settings
          apply without restarting the process.
        </p>
      </aside>
    </div>
  );
}

function Stat({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-2" : ""}>
      <dt className="text-[11px] uppercase tracking-[0.18em] text-white/35">{label}</dt>
      <dd className="mt-1 font-medium text-white/90">{value}</dd>
    </div>
  );
}
