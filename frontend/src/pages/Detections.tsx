import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

type Cls = "meteor" | "fireball" | "aircraft" | "satellite" | "unknown";

type Detection = {
  id: string;
  date: string;
  stem?: string;
  cls: Cls | string;
  match?: string | null;
  length_px?: number;
  aspect?: number;
  persist?: number;
  stars?: number;
  url: string;
  archive_url: string;
};

type Reel = { date: string; url: string; label: string };

type Index = {
  items: Detection[];
  counts: Record<string, number>;
  reels: Reel[];
  total: number;
};

type Night = { date: string; frames: number };

const FILTERS: Array<{ id: "all" | Cls; label: string }> = [
  { id: "all", label: "All" },
  { id: "meteor", label: "Meteors" },
  { id: "fireball", label: "Fireballs" },
  { id: "aircraft", label: "Aircraft" },
  { id: "satellite", label: "Satellites" },
  { id: "unknown", label: "Unknown" },
];

const CLS_COLOR: Record<string, string> = {
  meteor: "text-star",
  fireball: "text-orange-300",
  aircraft: "text-ice",
  satellite: "text-aurora",
  unknown: "text-white/55",
};

export default function Detections() {
  const client = useQueryClient();
  const [filter, setFilter] = useState<"all" | Cls>("all");
  const [active, setActive] = useState<Detection | null>(null);
  const [scanDay, setScanDay] = useState<string>("");
  const query = useQuery({
    queryKey: ["detections", filter],
    queryFn: () => {
      const q = filter === "all" ? "" : `?cls=${filter}`;
      return fetch(`/api/detections${q}`).then((r) => r.json() as Promise<Index>);
    },
    refetchInterval: 20_000,
  });
  const nights = useQuery({
    queryKey: ["archive-nights"],
    queryFn: () =>
      fetch("/api/archive").then((r) => r.json() as Promise<{ nights: Night[] }>),
  });
  const scan = useMutation({
    mutationFn: async (day: string) => {
      const res = await fetch(`/api/detections/scan/${day}`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      return res.json() as Promise<{ detections: number; frames: number }>;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ["detections"] }),
  });
  const items = query.data?.items ?? [];
  const counts = query.data?.counts ?? {};
  const reels = query.data?.reels ?? [];
  const grouped = useMemo(() => {
    const map = new Map<string, Detection[]>();
    for (const item of items) {
      const list = map.get(item.date) ?? [];
      list.push(item);
      map.set(item.date, list);
    }
    return [...map.entries()];
  }, [items]);
  const nightOptions = nights.data?.nights ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-4xl text-ice">Detections</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/50">
            Streaks found on consecutive night frames. Meteors are short and elongated; longer
            tracks that sit on a TLE or ADS-B contact are tagged satellite or aircraft. Crops live
            under <code className="text-white/70">processed/detections/</code>.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={scanDay}
            onChange={(event) => setScanDay(event.target.value)}
            className="rounded-full border border-white/12 bg-panel/80 px-3 py-1.5 text-sm text-white/80"
          >
            <option value="">Scan a night…</option>
            {nightOptions.map((night) => (
              <option key={night.date} value={night.date}>
                {night.date} · {night.frames} frames
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!scanDay || scan.isPending}
            onClick={() => scanDay && scan.mutate(scanDay)}
            className="rounded-full bg-ice px-4 py-1.5 text-sm text-ink disabled:opacity-40"
          >
            {scan.isPending ? "Scanning…" : "Scan night"}
          </button>
        </div>
      </div>

      {scan.isSuccess ? (
        <p className="text-sm text-aurora">
          {scan.data.detections} streak{scan.data.detections === 1 ? "" : "s"} from {scan.data.frames}{" "}
          frames.
        </p>
      ) : null}
      {scan.isError ? <p className="text-sm text-red-300">Scan failed.</p> : null}

      <div className="flex rounded-full bg-white/5 p-1 text-sm">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setFilter(item.id)}
            className={`rounded-full px-3 py-1.5 ${
              filter === item.id ? "bg-ice text-ink" : "text-white/55 hover:text-white"
            }`}
          >
            {item.label}
            <span className="ml-2 text-xs opacity-70">
              {item.id === "all" ? query.data?.total ?? 0 : counts[item.id] ?? 0}
            </span>
          </button>
        ))}
      </div>

      {reels.length ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {reels.map((reel) => (
            <article key={reel.url} className="overflow-hidden rounded-2xl border border-white/8 bg-panel/70">
              <video src={reel.url} className="aspect-video w-full bg-black object-cover" controls playsInline />
              <p className="p-3 text-sm text-white/80">
                {reel.label} · {reel.date}
              </p>
            </article>
          ))}
        </div>
      ) : null}

      {query.isLoading ? <p className="text-white/50">Loading detections…</p> : null}
      {!query.isLoading && items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-white/12 bg-panel/40 px-8 py-16 text-white/45">
          No streaks yet. They appear on saved night frames, or scan an archived night above.
        </p>
      ) : null}

      {grouped.map(([day, rows]) => (
        <section key={day} className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="display text-2xl text-star">{day}</h2>
            <Link to={`/archive/night/${day}`} className="text-sm text-ice/80 hover:text-ice">
              Open archive
            </Link>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setActive(item)}
                className="overflow-hidden rounded-2xl border border-white/8 bg-panel/70 text-left hover:border-ice/30"
              >
                <div className="aspect-4/3 overflow-hidden bg-black">
                  <img src={item.url} alt={item.cls} className="h-full w-full object-cover" />
                </div>
                <div className="p-4">
                  <p className={`text-sm font-medium capitalize ${CLS_COLOR[item.cls] ?? "text-white/80"}`}>
                    {item.cls}
                    {item.match ? ` · ${item.match}` : ""}
                  </p>
                  <p className="mt-1 text-xs text-white/45">
                    {item.length_px != null ? `${Math.round(item.length_px)} px` : ""}
                    {item.aspect != null ? ` · ${item.aspect.toFixed(1)}:1` : ""}
                  </p>
                  <p className="mt-1 text-xs text-white/35">{item.stem}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      ))}

      {active ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
          onClick={() => setActive(null)}
          role="dialog"
        >
          <div className="max-h-full w-full max-w-4xl" onClick={(event) => event.stopPropagation()}>
            <img src={active.url} alt={active.cls} className="max-h-[72vh] w-full rounded-2xl object-contain" />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
              <p className="text-white/70">
                <span className="capitalize">{active.cls}</span>
                {active.match ? ` · ${active.match}` : ""}
                {active.length_px != null ? ` · ${Math.round(active.length_px)} px` : ""}
                {` · ${active.date}`}
              </p>
              <div className="flex gap-2">
                <a href={active.url} className="rounded-full bg-ice px-3 py-1 text-ink" download>
                  Download
                </a>
                <Link to={active.archive_url} className="rounded-full bg-white/10 px-3 py-1">
                  Archive
                </Link>
                <button type="button" onClick={() => setActive(null)} className="rounded-full bg-white/10 px-3 py-1">
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
