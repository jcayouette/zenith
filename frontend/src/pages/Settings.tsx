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
  location: "Where the camera sits. Drives day/night, satellites, and aurora.",
  camera: "How Zenith talks to the sensor and what it saves.",
  picamera2: "Raspberry Pi CSI / HQ camera ISP controls.",
  indi: "USB astro cameras via indiserver (Phase 5).",
  mqtt_camera: "Remote Pi that owns its own libcamera module.",
  day: "Exposure profile while the sun is up.",
  night: "Exposure profile after astronomical night begins.",
  overlay: "Text and cardinals burned into archived frames.",
};

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

  if (!draft || !schemaQuery.data) {
    return <p className="text-white/50">Loading settings schema…</p>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-4xl text-ice">Settings</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/50">
            Generated from the Pydantic schema. Each control includes the description that will ship
            with the camera. Saving reloads the capture loop.
          </p>
        </div>
        <button
          type="button"
          onClick={() => save.mutate(draft)}
          className="rounded-full bg-ice px-5 py-2 text-sm font-medium text-ink hover:bg-white"
        >
          {save.isPending ? "Saving…" : "Save & apply"}
        </button>
      </div>
      {save.isError ? <p className="text-amber-300">{String(save.error)}</p> : null}
      {save.isSuccess ? <p className="text-aurora">Applied. Capture will pick this up on the next frame.</p> : null}

      {groups.map((group) => (
        <section key={group.key} className="rounded-3xl border border-white/8 bg-panel/70 p-6">
          <h2 className="font-serif text-2xl capitalize text-star">{group.key.replaceAll("_", " ")}</h2>
          <p className="mt-1 mb-6 text-sm text-white/45">{GROUP_COPY[group.key] ?? ""}</p>
          <div className="grid gap-5 md:grid-cols-2">
            {Object.entries(group.spec.properties ?? {}).map(([field, spec]) => (
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
      ))}
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
  const inputClass =
    "mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-ice/60";

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
        onClick={() => onChange(!value)}
        className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-medium ${
          value ? "bg-aurora/20 text-aurora" : "bg-white/10 text-white/50"
        }`}
      >
        {value ? "On" : "Off"}
      </button>
    );
  } else if (type === "integer" || type === "number") {
    control = (
      <input
        className={inputClass}
        type="number"
        step={type === "integer" ? 1 : "any"}
        min={spec.minimum}
        max={spec.maximum}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    );
  } else {
    control = (
      <input
        className={inputClass}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <label className="block">
      <span className="text-sm font-medium capitalize text-white/90">{title}</span>
      {control}
      {spec.description ? (
        <span className="mt-2 block text-xs leading-relaxed text-white/40">{spec.description}</span>
      ) : null}
    </label>
  );
}

function coerce(raw: string, spec: JsonSchema) {
  const type = Array.isArray(spec.type) ? spec.type[0] : spec.type;
  if (type === "integer" || type === "number") return Number(raw);
  if (type === "boolean") return raw === "true";
  return raw;
}
