import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { overlayCenter, overlayRadiusPx, type OverlayView } from "@/lib/overlayView";

export type MapStyle = "street" | "satellite" | "hybrid" | "terrain" | "elevation";

export const MAP_STYLE_OPTIONS: { id: MapStyle; label: string }[] = [
  { id: "street", label: "Streets" },
  { id: "satellite", label: "Satellite" },
  { id: "hybrid", label: "Hybrid" },
  { id: "terrain", label: "Terrain" },
  { id: "elevation", label: "Elevation" },
];

type Basemap = {
  url: string;
  maxZoom: number;
  minZoom?: number;
  subdomains?: string;
  attr: string;
  labels?: { url: string; subdomains?: string; maxZoom: number };
};

const BASEMAPS: Record<MapStyle, Basemap> = {
  street: {
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    maxZoom: 20,
    subdomains: "abcd",
    attr: "© OpenStreetMap © CARTO",
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxZoom: 19,
    attr: "© Esri",
  },
  hybrid: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxZoom: 19,
    attr: "© Esri © OSM © CARTO",
    labels: {
      url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png",
      subdomains: "abcd",
      maxZoom: 20,
    },
  },
  terrain: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    maxZoom: 19,
    attr: "© Esri",
  },
  elevation: {
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    maxZoom: 17,
    subdomains: "abc",
    attr: "© OpenStreetMap, SRTM © OpenTopoMap",
  },
};

type Props = {
  view: OverlayView;
  brightness: number;
  lat: number;
  lon: number;
  northAngle: number;
  mapKm: number;
  basemap: MapStyle;
};

export default function GroundMap({ view, brightness, lat, lon, northAngle, mapKm, basemap }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const rotRef = useRef<HTMLDivElement>(null);
  const mapElRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.Layer[]>([]);
  const viewRef = useRef(view);
  const latRef = useRef(lat);
  const lonRef = useRef(lon);
  const kmRef = useRef(mapKm);
  const angleRef = useRef(northAngle);
  const styleRef = useRef(basemap);
  viewRef.current = view;
  latRef.current = lat;
  lonRef.current = lon;
  kmRef.current = mapKm;
  angleRef.current = northAngle;
  styleRef.current = basemap;

  useEffect(() => {
    const el = mapElRef.current;
    if (!el) return;
    const map = L.map(el, {
      zoomControl: false,
      attributionControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      zoomSnap: 0,
      zoomDelta: 0.25,
      zoomAnimation: false,
      fadeAnimation: false,
      markerZoomAnimation: false,
      inertia: false,
      trackResize: false,
      maxZoom: 20,
      minZoom: 2,
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of layersRef.current) map.removeLayer(layer);
    const spec = BASEMAPS[basemap] ?? BASEMAPS.street;
    const base = L.tileLayer(spec.url, {
      maxZoom: spec.maxZoom,
      maxNativeZoom: spec.maxZoom,
      minZoom: spec.minZoom ?? 2,
      subdomains: spec.subdomains || "abc",
      detectRetina: true,
    }).addTo(map);
    const next: L.Layer[] = [base];
    if (spec.labels) {
      next.push(
        L.tileLayer(spec.labels.url, {
          maxZoom: spec.labels.maxZoom,
          maxNativeZoom: spec.labels.maxZoom,
          subdomains: spec.labels.subdomains || "abc",
          detectRetina: true,
          pane: "overlayPane",
        }).addTo(map),
      );
    }
    layersRef.current = next;
    applyView(map);
  }, [basemap]);

  useEffect(() => {
    const map = mapRef.current;
    const wrap = wrapRef.current;
    if (!map || !wrap) return;
    applyView(map);
    const ro = new ResizeObserver(() => applyView(map));
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [view.left, view.top, view.width, view.height, view.fit, lat, lon, mapKm, northAngle, basemap]);

  function applyView(map: L.Map) {
    const wrap = wrapRef.current;
    const rot = rotRef.current;
    if (!wrap || !rot) return;
    const v = viewRef.current;
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    if (w < 8 || h < 8 || v.width < 8 || v.height < 8) return;
    const [cx, cy] = overlayCenter(v);
    const radiusPx = overlayRadiusPx(v);
    wrap.style.clipPath = `circle(${Math.max(8, radiusPx)}px at ${cx}px ${cy}px)`;
    rot.style.transformOrigin = `${cx}px ${cy}px`;
    rot.style.transform = `rotate(${angleRef.current}deg)`;
    const spec = BASEMAPS[styleRef.current] ?? BASEMAPS.street;
    const mpp = (kmRef.current * 1000) / Math.max(radiusPx, 1);
    const cos = Math.max(0.2, Math.cos((latRef.current * Math.PI) / 180));
    const z = Math.log2((156543.03392 * cos) / Math.max(mpp, 1e-6));
    const zoom = Math.max(2, Math.min(spec.maxZoom, z));
    map.invalidateSize({ animate: false });
    map.setView([latRef.current, lonRef.current], zoom, { animate: false });
    const dx = cx - w / 2;
    const dy = cy - h / 2;
    if (Math.abs(dx) > 0.4 || Math.abs(dy) > 0.4) {
      map.panBy([dx, dy], { animate: false });
    }
  }

  const attr = (BASEMAPS[basemap] ?? BASEMAPS.street).attr;

  return (
    <div
      ref={wrapRef}
      className="pointer-events-none absolute inset-0 overflow-hidden"
      style={{ opacity: brightness }}
    >
      <div ref={rotRef} className="absolute inset-0">
        <div ref={mapElRef} className="zenith-leaflet absolute inset-0" />
      </div>
      <p className="absolute right-2 bottom-2 z-[500] text-[9px] text-slate-900/70">{attr}</p>
    </div>
  );
}
