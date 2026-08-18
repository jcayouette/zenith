import { memo, useEffect, useLayoutEffect, useRef } from "react";
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

const MERCATOR_PX = 156543.03392804097;

type Props = {
  view: OverlayView;
  viewRef: { current: OverlayView };
  stageW: number;
  stageH: number;
  brightness: number;
  lat: number;
  lon: number;
  northAngle: number;
  mapKm: number;
  basemap: MapStyle;
};

function mercatorZoom(lat: number, radiusPx: number, km: number, maxZoom: number) {
  const metersPerPx = (km * 1000) / Math.max(radiusPx, 1);
  const cos = Math.max(0.2, Math.abs(Math.cos((lat * Math.PI) / 180)));
  const z = Math.log2((MERCATOR_PX * cos) / Math.max(metersPerPx, 1e-6));
  return Math.max(2, Math.min(maxZoom, z));
}

function mapPad(w: number, h: number) {
  return Math.max(768, Math.round(Math.max(w, h) * 0.75));
}

function GroundMap({
  view,
  viewRef,
  stageW,
  stageH,
  brightness,
  lat,
  lon,
  northAngle,
  mapKm,
  basemap,
}: Props) {
  const clipRef = useRef<HTMLDivElement>(null);
  const rotRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const mapElRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.CircleMarker | null>(null);
  const layersRef = useRef<L.Layer[]>([]);
  const latRef = useRef(lat);
  const lonRef = useRef(lon);
  const angleRef = useRef(northAngle);
  const kmRef = useRef(mapKm);
  const stageRef = useRef({ w: stageW, h: stageH });
  const styleRef = useRef(basemap);
  const lastZRef = useRef(Number.NaN);
  const lastSizeRef = useRef({ w: 0, h: 0 });
  const baseRadiusRef = useRef(0);
  const ghostRef = useRef<HTMLElement | null>(null);
  latRef.current = lat;
  lonRef.current = lon;
  angleRef.current = northAngle;
  kmRef.current = mapKm;
  stageRef.current = { w: stageW, h: stageH };
  styleRef.current = basemap;

  useLayoutEffect(() => {
    const el = mapElRef.current;
    if (!el) return;
    const existing = (el as HTMLElement & { _leaflet_id?: number })._leaflet_id;
    if (existing) delete (el as HTMLElement & { _leaflet_id?: number })._leaflet_id;
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
      ghostRef.current?.remove();
      ghostRef.current = null;
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
      layersRef.current = [];
    };
  }, []);

  useLayoutEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of layersRef.current) map.removeLayer(layer);
    const spec = BASEMAPS[basemap] ?? BASEMAPS.street;
    const tileOpts = {
      maxZoom: spec.maxZoom,
      maxNativeZoom: spec.maxZoom,
      minZoom: spec.minZoom ?? 2,
      subdomains: spec.subdomains || "abc",
      detectRetina: false,
      keepBuffer: 4,
      updateWhenIdle: true,
      updateWhenZooming: false,
    };
    const next: L.Layer[] = [L.tileLayer(spec.url, tileOpts).addTo(map)];
    if (spec.labels) {
      next.push(
        L.tileLayer(spec.labels.url, {
          ...tileOpts,
          maxZoom: spec.labels.maxZoom,
          maxNativeZoom: spec.labels.maxZoom,
          subdomains: spec.labels.subdomains || "abc",
          pane: "overlayPane",
        }).addTo(map),
      );
    }
    layersRef.current = next;
    lastZRef.current = Number.NaN;
    calibrate(map);
  }, [basemap]);

  useLayoutEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    lastZRef.current = Number.NaN;
    lastSizeRef.current = { w: 0, h: 0 };
    calibrate(map);
  }, [stageW, stageH, lat, lon, mapKm]);

  useEffect(() => {
    let lastL = Number.NaN;
    let lastT = Number.NaN;
    let lastW = Number.NaN;
    let lastH = Number.NaN;
    let lastFit = Number.NaN;
    let lastScaleAt = 0;
    let pendingZoom = false;
    let raf = 0;
    const tick = () => {
      raf = window.requestAnimationFrame(tick);
      const map = mapRef.current;
      const v = viewRef.current;
      if (!map || v.width < 8) return;
      const moved = v.left !== lastL || v.top !== lastT;
      const scaled = v.width !== lastW || v.height !== lastH || v.fit !== lastFit;
      if (moved || scaled) {
        lastL = v.left;
        lastT = v.top;
        lastW = v.width;
        lastH = v.height;
        lastFit = v.fit;
        placeMap(v);
        if (scaled) {
          lastScaleAt = performance.now();
          pendingZoom = true;
        }
      } else if (pendingZoom && performance.now() - lastScaleAt > 180) {
        pendingZoom = false;
        setSiteZoom(map, v);
      }
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [viewRef]);

  function maxZ() {
    return (BASEMAPS[styleRef.current] ?? BASEMAPS.street).maxZoom;
  }

  function placeMap(v: OverlayView) {
    const clip = clipRef.current;
    const rot = rotRef.current;
    const wrap = wrapRef.current;
    const { w, h } = stageRef.current;
    if (!clip || !wrap || w < 8) return;
    const [cx, cy] = overlayCenter(v);
    const pad = mapPad(w, h);
    const mw = w + 2 * pad;
    const mh = h + 2 * pad;
    clip.style.clipPath = `circle(${Math.max(8, overlayRadiusPx(v))}px at ${cx}px ${cy}px)`;
    wrap.style.left = `${cx - mw / 2}px`;
    wrap.style.top = `${cy - mh / 2}px`;
    if (wrap.style.width !== `${mw}px`) wrap.style.width = `${mw}px`;
    if (wrap.style.height !== `${mh}px`) wrap.style.height = `${mh}px`;
    const radius = overlayRadiusPx(v);
    if (baseRadiusRef.current < 1) baseRadiusRef.current = radius;
    const k = radius / baseRadiusRef.current;
    wrap.style.transformOrigin = "50% 50%";
    wrap.style.transform = Math.abs(k - 1) < 0.002 ? "" : `scale(${k})`;
    if (rot) {
      rot.style.transformOrigin = `${cx}px ${cy}px`;
      rot.style.transform = angleRef.current ? `rotate(${angleRef.current}deg)` : "";
    }
  }

  function pinMarker(map: L.Map, site: L.LatLng) {
    if (!markerRef.current) {
      markerRef.current = L.circleMarker(site, {
        radius: 5,
        color: "#f8fafc",
        weight: 2,
        fillColor: "#f59e0b",
        fillOpacity: 0.95,
        interactive: false,
      }).addTo(map);
    } else {
      markerRef.current.setLatLng(site);
    }
  }

  function clearGhost() {
    ghostRef.current?.remove();
    ghostRef.current = null;
  }

  function freezeWrap() {
    const wrap = wrapRef.current;
    const rot = rotRef.current;
    if (!wrap || !rot) return;
    clearGhost();
    const ghost = wrap.cloneNode(true) as HTMLElement;
    ghost.style.pointerEvents = "none";
    ghost.style.zIndex = "2";
    rot.appendChild(ghost);
    ghostRef.current = ghost;
  }

  function tilesLoading(map: L.Map) {
    let loading = false;
    map.eachLayer((layer) => {
      if ((layer as { _loading?: boolean })._loading) loading = true;
    });
    return loading;
  }

  function whenPainted(map: L.Map, done: () => void) {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      done();
    };
    const wait = () => {
      if (tilesLoading(map)) {
        window.setTimeout(wait, 40);
        return;
      }
      window.requestAnimationFrame(() => window.requestAnimationFrame(finish));
    };
    window.setTimeout(wait, 0);
    window.setTimeout(finish, 600);
  }

  function setSiteZoom(map: L.Map, v: OverlayView) {
    const z = mercatorZoom(latRef.current, overlayRadiusPx(v), kmRef.current, maxZ());
    const site = L.latLng(latRef.current, lonRef.current);
    const wrap = wrapRef.current;
    const size = wrap
      ? { w: wrap.clientWidth, h: wrap.clientHeight }
      : { w: 0, h: 0 };
    const resized = size.w !== lastSizeRef.current.w || size.h !== lastSizeRef.current.h;
    const cur = map.getZoom();
    const zoomed = !Number.isFinite(cur) || cur < 2 || Math.abs(cur - z) >= 0.02;
    lastZRef.current = z;
    lastSizeRef.current = size;
    if (!resized && !zoomed) {
      baseRadiusRef.current = overlayRadiusPx(v);
      if (wrap) wrap.style.transform = "";
      return;
    }
    if (Number.isFinite(cur) && cur >= 2) freezeWrap();
    baseRadiusRef.current = overlayRadiusPx(v);
    if (wrap) wrap.style.transform = "";
    try {
      if (resized) map.invalidateSize({ animate: false });
      if (!Number.isFinite(cur) || cur < 2) map.setView(site, z, { animate: false });
      else map.setZoom(z, { animate: false });
    } catch {
      clearGhost();
      return;
    }
    pinMarker(map, site);
    whenPainted(map, clearGhost);
  }

  function calibrate(map: L.Map) {
    const v = viewRef.current;
    const { w, h } = stageRef.current;
    if (w < 8 || h < 8 || v.width < 8) return;
    placeMap(v);
    lastZRef.current = Number.NaN;
    lastSizeRef.current = { w: 0, h: 0 };
    baseRadiusRef.current = overlayRadiusPx(v);
    setSiteZoom(map, v);
  }

  const attr = (BASEMAPS[basemap] ?? BASEMAPS.street).attr;
  const [cx, cy] = overlayCenter(view);
  const radius = Math.max(8, overlayRadiusPx(view));
  const pad = mapPad(stageW, stageH);
  const mw = stageW + 2 * pad;
  const mh = stageH + 2 * pad;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" style={{ opacity: brightness }}>
      <div
        ref={clipRef}
        className="absolute inset-0 overflow-hidden"
        style={{ clipPath: `circle(${radius}px at ${cx}px ${cy}px)` }}
      >
        <div
          ref={rotRef}
          className="absolute inset-0"
          style={{
            transformOrigin: `${cx}px ${cy}px`,
            transform: northAngle ? `rotate(${northAngle}deg)` : undefined,
          }}
        >
          <div
            ref={wrapRef}
            className="absolute"
            style={{
              left: cx - mw / 2,
              top: cy - mh / 2,
              width: mw,
              height: mh,
              transformOrigin: "50% 50%",
              willChange: "transform",
            }}
          >
            <div ref={mapElRef} className="zenith-leaflet absolute inset-0" />
          </div>
        </div>
      </div>
      <p className="absolute right-2 bottom-2 z-[500] text-[9px] text-slate-900/70">{attr}</p>
    </div>
  );
}

function sameMap(prev: Props, next: Props) {
  return (
    prev.stageW === next.stageW &&
    prev.stageH === next.stageH &&
    prev.lat === next.lat &&
    prev.lon === next.lon &&
    prev.northAngle === next.northAngle &&
    prev.brightness === next.brightness &&
    prev.mapKm === next.mapKm &&
    prev.basemap === next.basemap &&
    prev.viewRef === next.viewRef
  );
}

export default memo(GroundMap, sameMap);
