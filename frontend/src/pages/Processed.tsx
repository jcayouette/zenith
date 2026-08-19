import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

type Category = "keograms" | "startrails" | "timelapses";

type ProcessedItem = {
  date: string;
  category: Category;
  key: string;
  name: string;
  label: string;
  url: string;
  bytes: number;
  mtime: number;
  media: "image" | "video";
  archive_url: string;
  meta?: { frames_used?: number; frames_seen?: number; mean_stars?: number };
};

type ProcessedIndex = {
  items: ProcessedItem[];
  counts: Record<Category, number>;
};

const FILTERS: Array<{ id: "all" | Category; label: string }> = [
  { id: "all", label: "All" },
  { id: "timelapses", label: "Timelapses" },
  { id: "keograms", label: "Keograms" },
  { id: "startrails", label: "Startrails" },
];

const FLIP_V_KEY = "zenith.processed.flipV";
const FLIP_H_KEY = "zenith.processed.flipH";

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function readFlag(key: string) {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function flipTransform(flipH: boolean, flipV: boolean) {
  const parts = [flipH ? "scaleX(-1)" : "", flipV ? "scaleY(-1)" : ""].filter(Boolean);
  return parts.length ? parts.join(" ") : undefined;
}

function useProcessedFlip() {
  const [flipV, setFlipV] = useState(() => readFlag(FLIP_V_KEY));
  const [flipH, setFlipH] = useState(() => readFlag(FLIP_H_KEY));
  useEffect(() => {
    try {
      localStorage.setItem(FLIP_V_KEY, flipV ? "1" : "0");
      localStorage.setItem(FLIP_H_KEY, flipH ? "1" : "0");
    } catch {
      /* ignore quota / private mode */
    }
  }, [flipV, flipH]);
  return {
    flipV,
    flipH,
    setFlipV,
    setFlipH,
    transform: flipTransform(flipH, flipV),
  };
}

export default function Processed() {
  const client = useQueryClient();
  const [filter, setFilter] = useState<"all" | Category>("all");
  const [active, setActive] = useState<ProcessedItem | null>(null);
  const [rebuildDay, setRebuildDay] = useState<string | null>(null);
  const flip = useProcessedFlip();
  const query = useQuery({
    queryKey: ["processed", filter],
    queryFn: () => {
      const q = filter === "all" ? "" : `?category=${filter}`;
      return fetch(`/api/processed${q}`).then((r) => r.json() as Promise<ProcessedIndex>);
    },
    refetchInterval: 15_000,
  });
  const rebuild = useMutation({
    mutationFn: async (day: string) => {
      const res = await fetch(`/api/processed/startrails/${day}`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      return res.json() as Promise<{ frames_used: number; frames_seen: number; wrote: boolean }>;
    },
    onMutate: (day) => setRebuildDay(day),
    onSettled: () => {
      setRebuildDay(null);
      void client.invalidateQueries({ queryKey: ["processed"] });
    },
  });
  const items = query.data?.items ?? [];
  const counts = query.data?.counts ?? { keograms: 0, startrails: 0, timelapses: 0 };
  const grouped = useMemo(() => {
    const map = new Map<string, ProcessedItem[]>();
    for (const item of items) {
      const list = map.get(item.date) ?? [];
      list.push(item);
      map.set(item.date, list);
    }
    return [...map.entries()];
  }, [items]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-4xl text-ice">Processed</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/50">
            Keograms, startrails, and timelapses live under{" "}
            <code className="text-white/70">processed/&#123;type&#125;/YYYY-MM-DD/</code>. Capture
            frames stay in Archive. Startrails max-stack every clear night frame; use Rebuild if a
            night finished before the stack was enabled.
          </p>
        </div>
        <div className="flex rounded-full bg-white/5 p-1 text-sm">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={`rounded-full px-4 py-1.5 ${
                filter === item.id ? "bg-ice text-ink" : "text-white/55 hover:text-white"
              }`}
            >
              {item.label}
              <span className="ml-2 text-xs opacity-70">
                {item.id === "all"
                  ? counts.keograms + counts.startrails + counts.timelapses
                  : counts[item.id]}
              </span>
            </button>
          ))}
        </div>
      </div>

      {query.isLoading ? <p className="text-white/50">Loading processed files…</p> : null}
      {!query.isLoading && items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-white/12 bg-panel/40 px-8 py-16 text-white/45">
          Nothing processed yet. Encode a RAW timelapse from Archive, or wait for sunrise products.
        </p>
      ) : null}

      {grouped.map(([day, rows]) => (
        <section key={day} className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="display text-2xl text-star">{day}</h2>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => rebuild.mutate(day)}
                disabled={rebuildDay === day}
                className="text-sm text-white/55 hover:text-ice disabled:text-white/30"
              >
                {rebuildDay === day ? "Stacking startrails…" : "Rebuild startrails"}
              </button>
              <Link to={`/archive/night/${day}`} className="text-sm text-ice/80 hover:text-ice">
                Open archive
              </Link>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((item) => (
              <button
                key={`${item.date}-${item.name}`}
                type="button"
                onClick={() => setActive(item)}
                className="overflow-hidden rounded-2xl border border-white/8 bg-panel/70 text-left hover:border-ice/30"
              >
                <div className="aspect-4/3 overflow-hidden bg-black">
                  {item.media === "video" ? (
                    <video
                      src={item.url}
                      className="h-full w-full object-cover"
                      style={flip.transform ? { transform: flip.transform } : undefined}
                      muted
                      playsInline
                    />
                  ) : (
                    <img
                      src={item.url}
                      alt={item.label}
                      className="h-full w-full object-cover"
                      style={flip.transform ? { transform: flip.transform } : undefined}
                    />
                  )}
                </div>
                <div className="p-4">
                  <p className="text-sm text-white/90">{item.label}</p>
                  <p className="mt-1 text-xs uppercase tracking-wide text-white/40">{item.category}</p>
                  {item.meta?.frames_used != null ? (
                    <p className="mt-1 text-xs text-white/45">
                      {item.meta.frames_used} stacked
                      {item.meta.mean_stars != null ? ` · ${Math.round(item.meta.mean_stars)} stars` : ""}
                    </p>
                  ) : null}
                  <p className="mt-1 text-xs text-white/35">{formatBytes(item.bytes)}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      ))}

      {active ? (
        <Viewer item={active} flip={flip} onClose={() => setActive(null)} />
      ) : null}
    </div>
  );
}

function Viewer({
  item,
  flip,
  onClose,
}: {
  item: ProcessedItem;
  flip: ReturnType<typeof useProcessedFlip>;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
      role="dialog"
    >
      <div className="max-h-full w-full max-w-5xl" onClick={(event) => event.stopPropagation()}>
        {item.media === "video" ? (
          <FlippedVideo src={item.url} transform={flip.transform} />
        ) : (
          <img
            src={item.url}
            alt={item.label}
            className="max-h-[78vh] w-full rounded-2xl object-contain"
            style={flip.transform ? { transform: flip.transform } : undefined}
          />
        )}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
          <p className="text-white/70">
            {item.label} · {item.date} · {formatBytes(item.bytes)}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => flip.setFlipV((value) => !value)}
              className={`rounded-full px-3 py-1 ${flip.flipV ? "bg-ice text-ink" : "bg-white/10"}`}
            >
              Flip V
            </button>
            <button
              type="button"
              onClick={() => flip.setFlipH((value) => !value)}
              className={`rounded-full px-3 py-1 ${flip.flipH ? "bg-ice text-ink" : "bg-white/10"}`}
            >
              Flip H
            </button>
            <button
              type="button"
              onClick={() => {
                const upsideDown = flip.flipH && flip.flipV;
                flip.setFlipH(!upsideDown);
                flip.setFlipV(!upsideDown);
              }}
              className={`rounded-full px-3 py-1 ${
                flip.flipH && flip.flipV ? "bg-ice text-ink" : "bg-white/10"
              }`}
            >
              180°
            </button>
            <a href={item.url} className="rounded-full bg-ice px-3 py-1 text-ink" download>
              Download
            </a>
            <Link to={item.archive_url} className="rounded-full bg-white/10 px-3 py-1">
              Archive
            </Link>
            <button type="button" onClick={onClose} className="rounded-full bg-white/10 px-3 py-1">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FlippedVideo({ src, transform }: { src: string; transform?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(true);
  const [muted, setMuted] = useState(true);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  return (
    <div>
      <div className="overflow-hidden rounded-2xl bg-black">
        <video
          ref={ref}
          src={src}
          className="max-h-[78vh] w-full origin-center"
          style={transform ? { transform } : undefined}
          autoPlay
          playsInline
          muted={muted}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
          onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
        />
      </div>
      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          className="rounded-full bg-white/10 px-3 py-1 text-sm"
          onClick={() => {
            const video = ref.current;
            if (!video) return;
            if (video.paused) void video.play();
            else video.pause();
          }}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={time}
          className="h-1 flex-1 accent-ice"
          onChange={(event) => {
            const video = ref.current;
            const next = Number(event.target.value);
            if (video) video.currentTime = next;
            setTime(next);
          }}
        />
        <span className="w-20 text-right text-xs text-white/45">
          {formatClock(time)} / {formatClock(duration)}
        </span>
        <button
          type="button"
          className="rounded-full bg-white/10 px-3 py-1 text-sm"
          onClick={() => {
            const video = ref.current;
            const next = !muted;
            setMuted(next);
            if (video) video.muted = next;
          }}
        >
          {muted ? "Unmute" : "Mute"}
        </button>
      </div>
    </div>
  );
}

function formatClock(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
