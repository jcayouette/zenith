import { SAT_KIND, satKindOf } from "@/components/SatLayer";
import SkyCard, { Metric, Row } from "@/components/SkyCard";

export type SatLive = {
  name?: string;
  norad?: string;
  kind?: string;
  alt?: number;
  az?: number;
  range_km?: number;
  object_id?: string;
};

export type Satcat = {
  norad?: string;
  name?: string | null;
  object_id?: string | null;
  object_type?: string | null;
  owner?: string | null;
  launch_date?: string | null;
  launch_site?: string | null;
  launch_site_name?: string | null;
  status?: string | null;
  period_min?: number | null;
  inclination_deg?: number | null;
  apogee_km?: number | null;
  perigee_km?: number | null;
  summary?: string | null;
  error?: string;
};

type Props = {
  sat: SatLive;
  satcat: Satcat | null;
  loading: boolean;
  onClose: () => void;
};

export default function SatInspector({ sat, satcat, loading, onClose }: Props) {
  const kind = satKindOf(sat);
  const color = SAT_KIND[kind].color;
  const site = satcat?.launch_site_name || satcat?.launch_site;
  const objectId = sat.object_id || satcat?.object_id;

  return (
    <SkyCard
      accent={color}
      kicker={SAT_KIND[kind].label}
      title={sat.name || sat.norad || "Satellite"}
      onClose={onClose}
    >
      {satcat?.summary ? (
        <p className="border-t border-white/8 px-3.5 py-2.5 text-[11px] leading-snug text-white/65">{satcat.summary}</p>
      ) : loading ? (
        <p className="border-t border-white/8 px-3.5 py-2.5 text-[11px] text-white/35">Catalog…</p>
      ) : null}
      <dl className="grid grid-cols-3 gap-px border-t border-white/8 bg-white/6 text-center">
        <Metric label="Alt" value={sat.alt != null ? `${sat.alt.toFixed(1)}°` : "—"} />
        <Metric label="Az" value={sat.az != null ? `${sat.az.toFixed(1)}°` : "—"} />
        <Metric label="Range" value={sat.range_km != null ? `${fmtKm(sat.range_km)} km` : "—"} />
      </dl>
      <dl className="space-y-1.5 px-3.5 py-3 text-[11px]">
        <Row label="NORAD" value={sat.norad || satcat?.norad || "—"} />
        {objectId ? <Row label="Object" value={String(objectId)} /> : null}
        {satcat?.owner ? <Row label="Owner" value={satcat.owner} /> : null}
        {satcat?.launch_date ? <Row label="Launched" value={fmtDate(satcat.launch_date)} /> : null}
        {site ? <Row label="Site" value={site} /> : null}
        {satcat?.status ? <Row label="Status" value={satcat.status} /> : null}
        {satcat?.object_type ? <Row label="Class" value={satcat.object_type} /> : null}
        {satcat?.period_min != null ? <Row label="Period" value={`${satcat.period_min.toFixed(1)} min`} /> : null}
        {satcat?.inclination_deg != null ? (
          <Row label="Incl." value={`${satcat.inclination_deg.toFixed(1)}°`} />
        ) : null}
        {satcat?.apogee_km != null && satcat?.perigee_km != null ? (
          <Row label="Orbit" value={`${fmtKm(satcat.perigee_km)}–${fmtKm(satcat.apogee_km)} km`} />
        ) : null}
        {!loading && satcat?.error ? <p className="text-white/35">{satcat.error}</p> : null}
      </dl>
    </SkyCard>
  );
}

function fmtKm(km: number) {
  return km >= 1000 ? km.toFixed(0) : km.toFixed(1);
}

function fmtDate(iso: string) {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]} ${m[1]}`;
}
