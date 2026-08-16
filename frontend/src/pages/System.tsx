import { useQuery } from "@tanstack/react-query";

type Alert = { level: "ok" | "warn" | "crit"; code: string; message: string };

type Temp = { id: string; label: string; celsius: number; source: string };

type Disk = {
  path: string;
  label: string;
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  percent: number;
};

type SystemHealth = {
  hostname: string;
  version: string;
  uptime_s: number;
  data_dir: string;
  clients: number;
  camera: { connected: boolean; released: boolean };
  capture: {
    capturing: boolean | null;
    backend: string | null;
    session: string | null;
    error: string | null;
  };
  cpu: {
    percent: number | null;
    load_1: number;
    load_5: number;
    load_15: number;
    load_percent: number;
    cores: number;
    freq_mhz: number | null;
    freq_max_mhz: number | null;
    governor: string | null;
  };
  memory: {
    total_bytes: number;
    available_bytes: number;
    used_bytes: number;
    percent: number;
    swap_total_bytes: number;
    swap_used_bytes: number;
    swap_percent: number;
  };
  disks: Disk[];
  temps: Temp[];
  power: {
    hex: string;
    throttled: boolean;
    core_volts: number | null;
    under_voltage_alarm: boolean | null;
    flags: Record<string, boolean>;
  };
  process: { pid: number; rss_bytes: number; threads: number };
  ntp?: { synchronized: boolean; ntp_enabled: boolean };
  alerts: Alert[];
};

export default function System() {
  const query = useQuery({
    queryKey: ["system"],
    queryFn: () =>
      fetch("/api/system").then((r) => {
        if (!r.ok) throw new Error("System status unavailable");
        return r.json() as Promise<SystemHealth>;
      }),
    refetchInterval: 2_000,
  });
  const data = query.data;
  const worst = worstLevel(data?.alerts ?? []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-4xl text-ice">System</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/50">
            Pi health for overnight capture: disk, heat, RAM, and CPU. Refreshes every two seconds.
          </p>
        </div>
        {data ? (
          <p className={`rounded-full px-4 py-1.5 text-sm ${badgeClass(worst)}`}>
            {data.hostname} · {data.alerts[0]?.message ?? "—"}
          </p>
        ) : null}
      </div>

      {query.isError ? <p className="text-amber-300">{String(query.error)}</p> : null}
      {!data && query.isLoading ? <p className="text-white/50">Reading sensors…</p> : null}

      {data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MeterCard
              title="CPU"
              value={`${(data.cpu.percent ?? data.cpu.load_percent).toFixed(0)}%`}
              detail={`${data.cpu.cores} cores · ${data.cpu.freq_mhz ?? "—"} MHz · load ${data.cpu.load_1.toFixed(2)}`}
              percent={data.cpu.percent ?? data.cpu.load_percent}
              warn={85}
              crit={95}
            />
            <MeterCard
              title="RAM"
              value={formatBytes(data.memory.available_bytes)}
              detail={`${formatBytes(data.memory.used_bytes)} used of ${formatBytes(data.memory.total_bytes)}`}
              percent={data.memory.percent}
              warn={85}
              crit={92}
              suffix="available"
            />
            {data.disks.map((disk) => (
              <MeterCard
                key={disk.path}
                title={disk.label}
                value={formatBytes(disk.free_bytes)}
                detail={`${formatBytes(disk.used_bytes)} used of ${formatBytes(disk.total_bytes)} · ${disk.path}`}
                percent={disk.percent}
                warn={85}
                crit={95}
                suffix="free"
              />
            ))}
            <MeterCard
              title="CPU temp"
              value={tempValue(data.temps, "cpu")}
              detail={tempLine(data.temps)}
              percent={tempBar(data.temps, "cpu")}
              warn={70}
              crit={80}
            />
          </div>

          <section className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-2xl border border-white/8 bg-panel/70 p-5 lg:col-span-2">
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Temperatures</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {data.temps.map((temp) => (
                  <div key={temp.id}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="text-white/70">{temp.label}</span>
                      <span className={temp.celsius >= 70 ? "text-amber-300" : "text-ice"}>
                        {temp.celsius.toFixed(1)}°C
                      </span>
                    </div>
                    <Bar percent={temp.celsius} warn={70} crit={80} />
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-white/8 bg-panel/70 p-5">
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Power</p>
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Core" value={data.power.core_volts != null ? `${data.power.core_volts.toFixed(3)} V` : "—"} />
                <Row label="Throttle" value={data.power.throttled ? "Yes" : "None"} warn={data.power.throttled} />
                <Row
                  label="Under-voltage"
                  value={data.power.under_voltage_alarm ? "Alarm" : "OK"}
                  warn={Boolean(data.power.under_voltage_alarm)}
                />
                <Row label="Flags" value={data.power.hex} />
              </dl>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-2xl border border-white/8 bg-panel/70 p-5">
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Device</p>
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Host" value={data.hostname} />
                <Row label="Uptime" value={formatUptime(data.uptime_s)} />
                <Row label="Zenith" value={data.version} />
                <Row label="PID" value={String(data.process.pid)} />
                <Row label="Zenith RAM" value={formatBytes(data.process.rss_bytes)} />
                <Row label="Threads" value={String(data.process.threads)} />
                <Row
                  label="NTP"
                  value={
                    data.ntp?.synchronized ? "Synced" : data.ntp?.ntp_enabled ? "Not synced" : "—"
                  }
                  warn={data.ntp != null && !data.ntp.synchronized}
                />
              </dl>
            </div>
            <div className="rounded-2xl border border-white/8 bg-panel/70 p-5">
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Capture</p>
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Camera" value={data.camera.connected ? "Connected" : data.camera.released ? "Released" : "Offline"} />
                <Row label="Pipeline" value={data.capture.capturing ? "Running" : "Idle"} />
                <Row label="Backend" value={data.capture.backend || "—"} />
                <Row label="Session" value={data.capture.session || "—"} />
                <Row label="Live clients" value={String(data.clients)} />
                <Row label="Governor" value={data.cpu.governor || "—"} />
              </dl>
              {data.capture.error ? <p className="mt-3 text-sm text-amber-300">{data.capture.error}</p> : null}
            </div>
            <div className="rounded-2xl border border-white/8 bg-panel/70 p-5">
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Alerts</p>
              <ul className="mt-4 space-y-2 text-sm">
                {data.alerts.map((alert, index) => (
                  <li key={`${alert.code}-${index}`} className={alertClass(alert.level)}>
                    {alert.message}
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-white/35">Archive lives at {data.data_dir}</p>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function MeterCard({
  title,
  value,
  detail,
  percent,
  warn,
  crit,
  suffix,
}: {
  title: string;
  value: string;
  detail: string;
  percent: number;
  warn: number;
  crit: number;
  suffix?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/8 bg-panel/70 p-5">
      <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">{title}</p>
      <p className="display mt-3 text-3xl text-ice">
        {value}
        {suffix ? <span className="ml-2 text-base text-white/40">{suffix}</span> : null}
      </p>
      <Bar percent={percent} warn={warn} crit={crit} />
      <p className="mt-2 text-xs text-white/40">{detail}</p>
    </div>
  );
}

function Bar({ percent, warn, crit }: { percent: number; warn: number; crit: number }) {
  const width = Math.min(100, Math.max(2, percent));
  const tone = percent >= crit ? "bg-red-400" : percent >= warn ? "bg-star" : "bg-ice";
  return (
    <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
      <div className={`h-full rounded-full transition-[width] duration-500 ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

function Row({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-white/45">{label}</dt>
      <dd className={warn ? "text-amber-300" : "text-white/85"}>{value}</dd>
    </div>
  );
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n < 1024 ** 4) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  return `${(n / 1024 ** 4).toFixed(2)} TB`;
}

function formatUptime(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h ${m}m`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

function tempValue(temps: Temp[], id: string) {
  const hit = temps.find((item) => item.id === id);
  return hit ? `${hit.celsius.toFixed(1)}°C` : "—";
}

function tempLine(temps: Temp[]) {
  return temps.map((item) => `${item.label} ${item.celsius.toFixed(0)}°`).join(" · ") || "No sensors";
}

function tempBar(temps: Temp[], id: string) {
  const hit = temps.find((item) => item.id === id);
  return hit ? hit.celsius : 0;
}

function worstLevel(alerts: Alert[]) {
  if (alerts.some((item) => item.level === "crit")) return "crit";
  if (alerts.some((item) => item.level === "warn")) return "warn";
  return "ok";
}

function badgeClass(level: string) {
  if (level === "crit") return "bg-red-500/20 text-red-200";
  if (level === "warn") return "bg-star/20 text-star";
  return "bg-aurora/15 text-aurora";
}

function alertClass(level: string) {
  if (level === "crit") return "text-red-200";
  if (level === "warn") return "text-star";
  return "text-aurora";
}
