import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

type JsonSchema = {
  title?: string;
  description?: string;
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  $defs?: Record<string, JsonSchema>;
  $ref?: string;
  enum?: Array<string | number | boolean>;
  minimum?: number;
  maximum?: number;
  default?: unknown;
  anyOf?: JsonSchema[];
};

type Values = Record<string, unknown>;

const GROUP_COPY: Record<string, string> = {
  location: "Site position for day/night, satellites, and aurora.",
  camera: "Sensor, archive, and capture pipeline.",
  picamera2: "Raspberry Pi HQ / IMX477 ISP.",
  indi: "USB astro cameras via indiserver.",
  mqtt_camera: "Remote Pi camera over MQTT.",
  day: "Exposure while the sun is up.",
  night: "Exposure after night begins.",
  overlay: "Text on the live JPEG and thumbs. Raw stays clean.",
  products: "Keograms, startrails, and timelapses.",
};

const GROUP_LABEL: Record<string, string> = {
  location: "Location",
  camera: "Camera",
  picamera2: "HQ camera",
  indi: "INDI",
  mqtt_camera: "MQTT camera",
  day: "Day",
  night: "Night",
  overlay: "Overlay",
  products: "Products",
};

function labelFor(key: string) {
  return GROUP_LABEL[key] ?? key.replaceAll("_", " ");
}

export default function Settings() {
  const client = useQueryClient();
  const schemaQuery = useQuery({
    queryKey: ["schema"],
    queryFn: () => fetch("/api/settings/schema").then((r) => r.json() as Promise<JsonSchema>),
  });
  const valuesQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => fetch("/api/settings").then((r) => r.json() as Promise<Values>),
  });
  const [draft, setDraft] = useState<Values | null>(null);
  const [active, setActive] = useState<string>("");

  useEffect(() => {
    if (valuesQuery.data) setDraft(valuesQuery.data);
  }, [valuesQuery.data]);

  const save = useMutation({
    mutationFn: async (payload: Values) => {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: (data) => {
      client.setQueryData(["settings"], data);
      setDraft(data);
    },
  });

  const groups = useMemo(() => {
    if (!schemaQuery.data || !draft) return [];
    const defs = schemaQuery.data.$defs ?? {};
    const props = schemaQuery.data.properties ?? {};
    return Object.entries(props).map(([key, spec]) => {
      const resolved = resolve(spec, defs);
      return { key, spec: resolved, value: (draft[key] ?? {}) as Values };
    });
  }, [schemaQuery.data, draft]);

  useEffect(() => {
    if (!groups.length) return;
    const fromHash = window.location.hash.replace(/^#/, "");
    const next = groups.some((g) => g.key === fromHash) ? fromHash : groups[0].key;
    setActive((current) => current || next);
  }, [groups]);

  function select(key: string) {
    setActive(key);
    window.history.replaceState(null, "", `#${key}`);
  }

  if (!draft || !schemaQuery.data) {
    return <p className="text-white/50">Loading settings…</p>;
  }

  const group = groups.find((g) => g.key === active) ?? groups[0];
  const fields = Object.entries(group.spec.properties ?? {});

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="display text-4xl text-ice">Settings</h1>
        <div className="flex items-center gap-3">
          {save.isError ? <p className="text-sm text-amber-300">{String(save.error)}</p> : null}
          {save.isSuccess ? <p className="text-sm text-aurora">Saved</p> : null}
          <button
            type="button"
            onClick={() => save.mutate(draft)}
            className="rounded-full bg-ice px-5 py-2 text-sm font-medium text-ink hover:bg-white"
          >
            {save.isPending ? "Saving…" : "Save & apply"}
          </button>
        </div>
      </div>

      <div className="lg:grid lg:grid-cols-[13.5rem_minmax(0,1fr)] lg:items-start lg:gap-6">
        <aside className="mb-4 lg:sticky lg:top-24 lg:mb-0">
          <nav className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
            {groups.map((item) => {
              const on = item.key === group.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => select(item.key)}
                  className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm transition ${
                    on ? "bg-white/10 text-ice" : "text-white/50 hover:bg-white/5 hover:text-white/80"
                  }`}
                >
                  {labelFor(item.key)}
                </button>
              );
            })}
          </nav>
        </aside>

        <section>
          <div className="mb-4">
            <h2 className="display text-2xl text-star">{labelFor(group.key)}</h2>
            {GROUP_COPY[group.key] ? (
              <p className="mt-1 text-sm text-white/40">{GROUP_COPY[group.key]}</p>
            ) : null}
          </div>
          {group.key === "camera" ? <CameraPower /> : null}
          <div className="divide-y divide-white/8 rounded-2xl border border-white/8 bg-panel/60">
            {fields.map(([field, spec]) => (
              <Field
                key={field}
                name={field}
                spec={resolve(spec, schemaQuery.data.$defs ?? {})}
                value={(group.value as Values)[field]}
                onChange={(next) =>
                  setDraft({
                    ...draft,
                    [group.key]: { ...(group.value as Values), [field]: next },
                  })
                }
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function CameraPower() {
  const [state, setState] = useState<{ connected: boolean; released: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const res = await fetch("/api/camera");
        if (!res.ok) return;
        const data = (await res.json()) as { connected: boolean; released: boolean };
        if (!stop) setState(data);
      } catch {
        /* ignore */
      }
    }
    void tick();
    const id = window.setInterval(() => void tick(), 2000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  async function toggle() {
    if (!state) return;
    setBusy(true);
    try {
      const path = state.released ? "/api/camera/connect" : "/api/camera/disconnect";
      const res = await fetch(path, { method: "POST" });
      if (res.ok) setState((await res.json()) as { connected: boolean; released: boolean });
    } finally {
      setBusy(false);
    }
  }

  const on = Boolean(state && !state.released);

  return (
    <div className="mb-4 flex items-center justify-between gap-4 rounded-2xl border border-white/8 bg-panel/60 px-5 py-4">
      <div>
        <p className="text-sm text-white/90">Sensor</p>
        <p className="mt-0.5 text-xs text-white/40">
          {on
            ? "Camera is open. Disconnect before unplugging the CSI cable."
            : "Camera is released. Safe to unplug, or connect to start capturing again."}
        </p>
      </div>
      <button
        type="button"
        onClick={() => void toggle()}
        disabled={busy || !state}
        className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${
          on ? "bg-white/10 text-white/80 hover:bg-red-500/20 hover:text-red-200" : "bg-aurora/20 text-aurora"
        }`}
      >
        {busy ? "Working…" : on ? "Disconnect camera" : "Connect camera"}
      </button>
    </div>
  );
}

function resolve(spec: JsonSchema, defs: Record<string, JsonSchema>): JsonSchema {
  if (spec.$ref) {
    const name = spec.$ref.split("/").pop() ?? "";
    return defs[name] ?? spec;
  }
  if (spec.anyOf) {
    const nonNull = spec.anyOf.find((s) => s.type !== "null" && s.$ref !== undefined) ?? spec.anyOf[0];
    return resolve(nonNull, defs);
  }
  return spec;
}

function Field({
  name,
  spec,
  value,
  onChange,
}: {
  name: string;
  spec: JsonSchema;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const type = Array.isArray(spec.type) ? spec.type[0] : spec.type;
  const title = spec.title ?? name.replaceAll("_", " ");
  const wide = type === "string" && !spec.enum;
  const inputClass =
    "w-full rounded-lg border border-white/10 bg-black/35 px-3 py-1.5 text-sm text-white outline-none focus:border-ice/50";

  let control: ReactNode;
  if (spec.enum) {
    control = (
      <select className={inputClass} value={String(value ?? "")} onChange={(e) => onChange(coerce(e.target.value, spec))}>
        {spec.enum.map((opt) => (
          <option key={String(opt)} value={String(opt)}>
            {String(opt)}
          </option>
        ))}
      </select>
    );
  } else if (type === "boolean") {
    control = (
      <button
        type="button"
        role="switch"
        aria-checked={Boolean(value)}
        onClick={() => onChange(!value)}
        className={`relative h-6 w-10 shrink-0 rounded-full transition ${value ? "bg-aurora" : "bg-white/15"}`}
      >
        <span
          className="absolute top-0.5 h-5 w-5 rounded-full bg-white transition"
          style={{ left: value ? "1.125rem" : "0.125rem" }}
        />
      </button>
    );
  } else if (type === "integer" || type === "number") {
    control = (
      <input
        className={`${inputClass} text-right tabular-nums`}
        type="number"
        step={type === "integer" ? 1 : 0.01}
        min={spec.minimum}
        max={spec.maximum}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    );
  } else {
    control = (
      <input className={inputClass} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    );
  }

  return (
    <div className={`px-5 py-3.5 ${wide ? "space-y-2" : "flex items-center justify-between gap-6"}`}>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-white/90">{title}</p>
        {spec.description ? (
          <p className="mt-0.5 line-clamp-1 text-xs text-white/35" title={spec.description}>
            {spec.description}
          </p>
        ) : null}
      </div>
      <div className={wide ? "w-full" : "w-40 shrink-0"}>{control}</div>
    </div>
  );
}

function coerce(raw: string, spec: JsonSchema) {
  const type = Array.isArray(spec.type) ? spec.type[0] : spec.type;
  if (type === "integer" || type === "number") return Number(raw);
  if (type === "boolean") return raw === "true";
  return raw;
}
