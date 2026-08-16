import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ConfirmDialog from "@/components/ConfirmDialog";

type ProductMap = Record<string, string>;

type SessionCard = {
  date: string;
  kind: "night" | "day";
  frames: number;
  latest: string | null;
  thumb_url: string | null;
  products: ProductMap;
};

type ArchiveIndex = {
  nights: SessionCard[];
  days: SessionCard[];
};

type FrameItem = {
  name: string;
  thumb_url: string;
  preview_url: string;
  raw_url: string | null;
  png_url: string | null;
  jpeg_url: string | null;
};

type EncodeProgress = {
  phase: string;
  label: string;
  total: number;
  done: number;
  developed: number;
  skipped: number;
  eta_seconds: number | null;
  percent: number;
  error: string | null;
};

type SessionDetail = {
  date: string;
  kind: "night" | "day";
  frames: FrameItem[];
  total: number;
  offset: number;
  limit: number;
  products: ProductMap;
  encoding?: boolean;
  encode?: EncodeProgress | null;
};

type PendingDelete =
  | { scope: "session"; kind: "night" | "day"; date: string; frames: number }
  | { scope: "kind"; kind: "night" | "day"; sessions: number; frames: number }
  | { scope: "all"; nights: number; days: number; frames: number };

const PRODUCT_LABELS: Record<string, string> = {
  keogram: "Keogram",
  keogram_realtime: "Realtime keogram",
  startrails: "Startrails",
  timelapse: "Timelapse",
  mini: "Mini timelapse",
};

async function deletePath(path: string) {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error((await res.text()) || "Delete failed");
  return res.json() as Promise<{ files?: number }>;
}

function deleteCopy(pending: PendingDelete) {
  if (pending.scope === "session") {
    const label = pending.kind === "night" ? "night" : "day";
    return {
      title: `Delete this ${label}?`,
      body: `This removes ${pending.frames} frame${pending.frames === 1 ? "" : "s"} for ${pending.date} (DNG, PNG, JPEG, thumbs). Keograms, startrails, and timelapses on Processed stay. This cannot be undone.`,
      confirmLabel: `Delete ${label}`,
      path: `/api/archive/${pending.kind}/${pending.date}`,
    };
  }
  if (pending.scope === "kind") {
    const label = pending.kind === "night" ? "nights" : "days";
    return {
      title: `Delete all ${label}?`,
      body: `This removes ${pending.sessions} ${label} (${pending.frames} frame${pending.frames === 1 ? "" : "s"}). Processed keograms, startrails, and timelapses stay. This cannot be undone.`,
      confirmLabel: `Delete ${label}`,
      path: `/api/archive/${label}`,
    };
  }
  return {
    title: "Delete the entire archive?",
    body: `This removes ${pending.nights} night${pending.nights === 1 ? "" : "s"} and ${pending.days} day${pending.days === 1 ? "" : "s"} (${pending.frames} frames). Processed outputs, config, darks, and the live camera are not touched. This cannot be undone.`,
    confirmLabel: "Delete everything",
    path: "/api/archive/all",
  };
}

export default function Archive() {
  const { kind, date } = useParams();
  if (kind && date) {
    return <SessionPage kind={kind} date={date} />;
  }
  return <IndexPage />;
}

function IndexPage() {
  const client = useQueryClient();
  const [tab, setTab] = useState<"nights" | "days">("nights");
  const [pending, setPending] = useState<PendingDelete | null>(null);
  const query = useQuery({
    queryKey: ["archive"],
    queryFn: () => fetch("/api/archive").then((r) => r.json() as Promise<ArchiveIndex>),
    refetchInterval: 15_000,
  });
  const nights = query.data?.nights ?? [];
  const days = query.data?.days ?? [];
  const sessions = tab === "nights" ? nights : days;
  const nightFrames = nights.reduce((sum, item) => sum + item.frames, 0);
  const dayFrames = days.reduce((sum, item) => sum + item.frames, 0);
  const totalFrames = nightFrames + dayFrames;

  const remove = useMutation({
    mutationFn: (path: string) => deletePath(path),
    onSuccess: () => {
      setPending(null);
      void client.invalidateQueries({ queryKey: ["archive"] });
    },
  });

  const copy = pending ? deleteCopy(pending) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-4xl text-ice">Archive</h1>
          <p className="mt-2 text-sm text-white/50">
            {nights.length} night{nights.length === 1 ? "" : "s"} · {days.length} day{days.length === 1 ? "" : "s"} ·{" "}
            {totalFrames} frame{totalFrames === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex rounded-full bg-white/5 p-1 text-sm">
          {(["nights", "days"] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`rounded-full px-4 py-1.5 capitalize ${
                tab === key ? "bg-ice text-ink" : "text-white/55 hover:text-white"
              }`}
            >
              {key}
              <span className="ml-2 text-xs opacity-70">{key === "nights" ? nights.length : days.length}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/8 bg-panel/60 px-4 py-3">
        <p className="text-sm text-white/45">Manage captured sessions. Deletes cannot be undone.</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={nights.length === 0}
            onClick={() =>
              setPending({ scope: "kind", kind: "night", sessions: nights.length, frames: nightFrames })
            }
            className="rounded-full px-3 py-1.5 text-sm text-white/55 hover:bg-white/8 hover:text-red-200 disabled:opacity-30"
          >
            Delete nights
          </button>
          <button
            type="button"
            disabled={days.length === 0}
            onClick={() => setPending({ scope: "kind", kind: "day", sessions: days.length, frames: dayFrames })}
            className="rounded-full px-3 py-1.5 text-sm text-white/55 hover:bg-white/8 hover:text-red-200 disabled:opacity-30"
          >
            Delete days
          </button>
          <button
            type="button"
            disabled={totalFrames === 0 && nights.length === 0 && days.length === 0}
            onClick={() =>
              setPending({ scope: "all", nights: nights.length, days: days.length, frames: totalFrames })
            }
            className="rounded-full px-3 py-1.5 text-sm text-red-300/80 hover:bg-red-500/15 hover:text-red-200 disabled:opacity-30"
          >
            Delete all
          </button>
        </div>
      </div>

      {query.isLoading ? <p className="text-white/50">Loading archive…</p> : null}
      {!query.isLoading && sessions.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-white/12 bg-panel/40 px-8 py-16 text-white/45">
          No {tab} saved yet.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sessions.map((session) => (
            <article
              key={`${session.kind}-${session.date}`}
              className="relative overflow-hidden rounded-2xl border border-white/8 bg-panel/70"
            >
              <Link to={`/archive/${session.kind}/${session.date}`} className="block">
                <div className="relative aspect-4/3 bg-black">
                  {session.thumb_url ? (
                    <img
                      src={session.thumb_url}
                      alt={`${session.kind} ${session.date}`}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-white/30">No frames</div>
                  )}
                  <span className="absolute top-3 left-3 rounded-full bg-black/55 px-2.5 py-0.5 text-[11px] uppercase tracking-wide text-ice backdrop-blur-sm">
                    {session.kind}
                  </span>
                </div>
                <div className="p-4 pr-24">
                  <p className="display text-2xl text-star">{session.date}</p>
                  <p className="mt-1 text-sm text-white/50">
                    {session.frames} frame{session.frames === 1 ? "" : "s"}
                  </p>
                  {Object.keys(session.products).length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {Object.keys(session.products).map((key) => (
                        <span
                          key={key}
                          className="rounded-full bg-white/8 px-2 py-0.5 text-[11px] uppercase tracking-wide text-ice/80"
                        >
                          {PRODUCT_LABELS[key] ?? key}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </Link>
              <button
                type="button"
                onClick={() =>
                  setPending({
                    scope: "session",
                    kind: session.kind,
                    date: session.date,
                    frames: session.frames,
                  })
                }
                className="absolute right-3 bottom-4 rounded-full bg-white/8 px-3 py-1.5 text-sm text-white/60 hover:bg-red-500/20 hover:text-red-200"
              >
                Delete
              </button>
            </article>
          ))}
        </div>
      )}

      {remove.isError ? <p className="text-sm text-amber-300">{String(remove.error)}</p> : null}

      <ConfirmDialog
        open={Boolean(pending)}
        title={copy?.title ?? ""}
        body={copy?.body ?? ""}
        confirmLabel={copy?.confirmLabel}
        busy={remove.isPending}
        onCancel={() => {
          if (!remove.isPending) setPending(null);
        }}
        onConfirm={() => {
          if (copy) remove.mutate(copy.path);
        }}
      />
    </div>
  );
}

function SessionPage({ kind, date }: { kind: string; date: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [active, setActive] = useState<FrameItem | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [encoding, setEncoding] = useState(false);
  const [videoKey, setVideoKey] = useState(0);
  const limit = 120;
  const query = useQuery({
    queryKey: ["archive", kind, date, offset],
    queryFn: () =>
      fetch(`/api/archive/${kind}/${date}?offset=${offset}&limit=${limit}`).then((r) => {
        if (!r.ok) throw new Error("Session not found");
        return r.json() as Promise<SessionDetail>;
      }),
    refetchInterval: encoding ? 8_000 : 20_000,
  });
  const data = query.data;
  const encodeTl = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/archive/${kind}/${date}/timelapse`, { method: "POST" });
      if (!res.ok) throw new Error((await res.text()) || "Encode failed");
      return res.json() as Promise<{ status?: string }>;
    },
    onSuccess: () => {
      setEncoding(true);
      void client.invalidateQueries({ queryKey: ["timelapse", kind, date] });
      void client.invalidateQueries({ queryKey: ["archive", kind, date] });
    },
  });
  const progressQuery = useQuery({
    queryKey: ["timelapse", kind, date],
    queryFn: () =>
      fetch(`/api/archive/${kind}/${date}/timelapse`).then((r) => {
        if (!r.ok) throw new Error("Progress unavailable");
        return r.json() as Promise<{ encoding: boolean; encode: EncodeProgress | null }>;
      }),
    refetchInterval: encoding ? 2_000 : false,
    enabled: encoding || encodeTl.isPending || Boolean(data?.encoding),
  });
  const products = data?.products ?? {};
  const pages = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, Math.ceil(data.total / limit));
  }, [data, limit]);
  const page = Math.floor(offset / limit) + 1;
  const sessionKind = kind === "days" || kind === "day" ? "day" : "night";
  const pending: PendingDelete = {
    scope: "session",
    kind: sessionKind,
    date,
    frames: data?.total ?? 0,
  };
  const copy = deleteCopy(pending);

  const remove = useMutation({
    mutationFn: () => deletePath(copy.path),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["archive"] });
      navigate("/archive");
    },
  });

  useEffect(() => {
    const running = Boolean(progressQuery.data?.encoding ?? data?.encoding);
    if (running) setEncoding(true);
    if (encoding && progressQuery.data && progressQuery.data.encoding === false) {
      setEncoding(false);
      setVideoKey(Date.now());
      void client.invalidateQueries({ queryKey: ["archive"] });
      void client.invalidateQueries({ queryKey: ["processed"] });
    }
  }, [client, data, encoding, progressQuery.data]);

  const busy = encodeTl.isPending || encoding || Boolean(data?.encoding) || Boolean(progressQuery.data?.encoding);
  const progress = progressQuery.data?.encode ?? data?.encode ?? null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <button
            type="button"
            onClick={() => navigate("/archive")}
            className="text-sm text-ice/80 hover:text-ice"
          >
            ← All sessions
          </button>
          <h1 className="display mt-3 text-4xl capitalize text-ice">
            {kind} {date}
          </h1>
          <p className="mt-2 text-sm text-white/50">
            {data ? `${data.total} archived frame${data.total === 1 ? "" : "s"}` : "Loading…"}
            {kind === "night" ? (
              <>
                {" · "}
                <Link to="/processed" className="text-ice/80 hover:text-ice">
                  Processed outputs
                </Link>
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => encodeTl.mutate()}
            disabled={busy}
            className="rounded-full bg-ice/90 px-4 py-2 text-sm font-medium text-ink hover:bg-white disabled:opacity-40"
          >
            {busy ? buttonLabel(progress) : "Encode RAW timelapse"}
          </button>
          <button
            type="button"
            onClick={() => setConfirm(true)}
            className="rounded-full bg-white/8 px-4 py-2 text-sm text-white/70 hover:bg-red-500/20 hover:text-red-200"
          >
            Delete this {sessionKind}
          </button>
        </div>
      </div>

      {Object.keys(products).length > 0 ? (
        <section className="grid gap-4 lg:grid-cols-2">
          {products.keogram_realtime || products.keogram ? (
            <ProductImage
              title="Keogram"
              src={products.keogram_realtime || products.keogram}
              note={products.keogram ? "Nightly copy saved at sunrise" : "Updating each frame"}
            />
          ) : null}
          {products.startrails ? (
            <ProductImage title="Startrails" src={products.startrails} note="Max stack of clear frames" />
          ) : null}
          {products.mini || products.timelapse ? (
            <div className="rounded-2xl border border-white/8 bg-panel/70 p-4 lg:col-span-2">
              <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Timelapse</p>
              <video
                className="mt-3 w-full rounded-2xl bg-black"
                controls
                src={`${products.mini || products.timelapse}${videoKey ? `?t=${videoKey}` : ""}`}
              />
              <div className="mt-3 flex flex-wrap gap-3 text-sm">
                {products.mini ? (
                  <a className="text-ice hover:underline" href={products.mini}>
                    Mini preview
                  </a>
                ) : null}
                {products.timelapse ? (
                  <a className="text-ice hover:underline" href={products.timelapse}>
                    Full-night backup
                  </a>
                ) : null}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {query.isError ? <p className="text-amber-300">{String(query.error)}</p> : null}
      {remove.isError ? <p className="text-sm text-amber-300">{String(remove.error)}</p> : null}
      {encodeTl.isError ? <p className="text-sm text-amber-300">{String(encodeTl.error)}</p> : null}
      {busy ? <EncodeProgressBar progress={progress} /> : null}

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="display text-2xl text-star">Frames</h2>
          {data && data.total > limit ? (
            <div className="flex items-center gap-2 text-sm">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                className="rounded-full bg-white/8 px-3 py-1 disabled:opacity-30"
              >
                Prev
              </button>
              <span className="text-white/50">
                {page} / {pages}
              </span>
              <button
                type="button"
                disabled={page >= pages}
                onClick={() => setOffset(offset + limit)}
                className="rounded-full bg-white/8 px-3 py-1 disabled:opacity-30"
              >
                Next
              </button>
            </div>
          ) : null}
        </div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
          {(data?.frames ?? []).map((frame) => (
            <button
              key={frame.name}
              type="button"
              onClick={() => setActive(frame)}
              className="overflow-hidden rounded-xl bg-black ring-1 ring-white/8 hover:ring-ice/50"
            >
              <img src={frame.thumb_url} alt={frame.name} className="aspect-4/3 w-full object-cover" />
            </button>
          ))}
        </div>
      </section>

      {active ? (
        <Lightbox
          frame={active}
          frames={data?.frames ?? []}
          onClose={() => setActive(null)}
          onSelect={setActive}
        />
      ) : null}

      <ConfirmDialog
        open={confirm}
        title={copy.title}
        body={copy.body}
        confirmLabel={copy.confirmLabel}
        busy={remove.isPending}
        onCancel={() => {
          if (!remove.isPending) setConfirm(false);
        }}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

function ProductImage({ title, src, note }: { title: string; src: string; note: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-panel/70 p-4">
      <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">{title}</p>
      <img src={src} alt={title} className="mt-3 w-full rounded-2xl bg-black object-contain" />
      <p className="mt-2 text-xs text-white/40">{note}</p>
    </div>
  );
}

function buttonLabel(progress: EncodeProgress | null) {
  if (progress?.phase === "encoding") return "Encoding video…";
  if (progress && progress.total > 0) {
    return `Developing ${progress.done}/${progress.total}`;
  }
  return "Developing RAW…";
}

function formatEta(seconds: number | null, developed: number) {
  if (seconds == null) return developed < 2 ? "estimating…" : null;
  if (seconds < 45) return "under a minute left";
  if (seconds < 90) return "~1 min left";
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `~${mins} min left`;
  const hours = Math.floor(mins / 60);
  const rest = mins % 60;
  return rest ? `~${hours}h ${rest}m left` : `~${hours}h left`;
}

function EncodeProgressBar({ progress }: { progress: EncodeProgress | null }) {
  const percent = progress?.percent ?? 0;
  const eta = progress ? formatEta(progress.eta_seconds, progress.developed) : "starting…";
  const count =
    progress && progress.total > 0
      ? `${progress.done.toLocaleString()} / ${progress.total.toLocaleString()} frames`
      : "Preparing frames…";
  return (
    <div className="rounded-2xl border border-white/8 bg-panel/70 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <p className="text-white/80">{progress?.label || "Developing 12-bit DNG"}</p>
        <p className="text-white/45">{eta}</p>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-ice transition-[width] duration-500"
          style={{ width: `${Math.min(100, Math.max(2, percent))}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-white/40">
        {count}
        {progress && progress.skipped > 0 ? ` · ${progress.skipped.toLocaleString()} already developed` : ""}
        . Live capture keeps running.
      </p>
      {progress?.error ? <p className="mt-2 text-sm text-amber-300">{progress.error}</p> : null}
    </div>
  );
}

function Lightbox({
  frame,
  frames,
  onClose,
  onSelect,
}: {
  frame: FrameItem;
  frames: FrameItem[];
  onClose: () => void;
  onSelect: (frame: FrameItem) => void;
}) {
  const index = frames.findIndex((item) => item.name === frame.name);
  const prev = index > 0 ? frames[index - 1] : null;
  const next = index >= 0 && index < frames.length - 1 ? frames[index + 1] : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
        if (event.key === "ArrowLeft" && prev) onSelect(prev);
        if (event.key === "ArrowRight" && next) onSelect(next);
      }}
      role="dialog"
      tabIndex={-1}
    >
      <div className="max-h-full max-w-6xl" onClick={(event) => event.stopPropagation()}>
        <img src={frame.preview_url} alt={frame.name} className="max-h-[82vh] rounded-2xl object-contain" />
        <div className="mt-3 flex items-center justify-between gap-4 text-sm">
          <p className="text-white/70">{frame.name}</p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!prev}
              onClick={() => prev && onSelect(prev)}
              className="rounded-full bg-white/10 px-3 py-1 disabled:opacity-30"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={!next}
              onClick={() => next && onSelect(next)}
              className="rounded-full bg-white/10 px-3 py-1 disabled:opacity-30"
            >
              Next
            </button>
            {frame.raw_url ? (
              <a href={frame.raw_url} className="rounded-full bg-ice px-3 py-1 text-ink">
                Raw
              </a>
            ) : null}
            {frame.png_url ? (
              <a href={frame.png_url} className="rounded-full bg-white/10 px-3 py-1">
                PNG
              </a>
            ) : null}
            <button type="button" onClick={onClose} className="rounded-full bg-white/10 px-3 py-1">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
