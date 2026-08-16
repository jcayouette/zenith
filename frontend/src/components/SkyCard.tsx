import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

const DEFAULT_TOP = 112;
const MARGIN = 12;

type Props = {
  accent: string;
  kicker: string;
  title: string;
  onClose: () => void;
  children: ReactNode;
};

export default function SkyCard({ accent, kicker, title, onClose, children }: Props) {
  const cardRef = useRef<HTMLElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);

  const clamp = useCallback((x: number, y: number) => {
    const el = cardRef.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return { x, y };
    const maxX = Math.max(MARGIN, parent.clientWidth - el.offsetWidth - MARGIN);
    const maxY = Math.max(MARGIN, parent.clientHeight - el.offsetHeight - MARGIN);
    return {
      x: Math.min(maxX, Math.max(MARGIN, x)),
      y: Math.min(maxY, Math.max(MARGIN, y)),
    };
  }, []);

  useEffect(() => {
    if (!pos) return;
    const onWin = () => setPos((p) => (p ? clamp(p.x, p.y) : p));
    window.addEventListener("resize", onWin);
    return () => window.removeEventListener("resize", onWin);
  }, [pos, clamp]);

  function startDrag(e: ReactPointerEvent) {
    if (e.button !== 0) return;
    const el = cardRef.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    const rect = el.getBoundingClientRect();
    const prect = parent.getBoundingClientRect();
    const origin = pos ?? { x: rect.left - prect.left, y: rect.top - prect.top };
    if (!pos) setPos(origin);
    dragRef.current = { dx: e.clientX - (prect.left + origin.x), dy: e.clientY - (prect.top + origin.y) };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onDrag(e: ReactPointerEvent) {
    const drag = dragRef.current;
    const parent = cardRef.current?.offsetParent as HTMLElement | null;
    if (!drag || !parent) return;
    const prect = parent.getBoundingClientRect();
    setPos(clamp(e.clientX - prect.left - drag.dx, e.clientY - prect.top - drag.dy));
  }

  const maxH = pos
    ? `calc(100% - ${pos.y + MARGIN}px)`
    : `calc(100% - ${DEFAULT_TOP + MARGIN}px)`;

  return (
    <aside
      ref={cardRef}
      className="pointer-events-auto absolute z-20 flex w-[min(19.5rem,calc(100%-1.5rem))] flex-col overflow-hidden rounded-2xl border border-white/12 bg-slate-950/88 shadow-xl backdrop-blur-md"
      style={
        pos
          ? { left: pos.x, top: pos.y, right: "auto", maxHeight: maxH }
          : { top: DEFAULT_TOP, right: MARGIN, maxHeight: maxH }
      }
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      onWheel={(e) => e.stopPropagation()}
    >
      <div
        className="flex cursor-grab items-start gap-3 px-3.5 py-3 active:cursor-grabbing"
        style={{ boxShadow: `inset 3px 0 0 ${accent}` }}
        title="Drag to move"
        onPointerDown={startDrag}
        onPointerMove={onDrag}
        onPointerUp={() => {
          dragRef.current = null;
        }}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
      >
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-white/40">
            <span aria-hidden className="inline-flex flex-col gap-0.5 opacity-50">
              <span className="h-0.5 w-2.5 rounded-full bg-current" />
              <span className="h-0.5 w-2.5 rounded-full bg-current" />
            </span>
            {kicker}
          </p>
          <p className="mt-0.5 truncate text-base font-semibold leading-tight" style={{ color: accent }}>
            {title}
          </p>
        </div>
        <button
          type="button"
          className="cursor-pointer rounded-lg px-1.5 py-0.5 text-sm text-white/40 hover:bg-white/10 hover:text-white"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>
      </div>
      <div className="min-h-0 overflow-y-auto">{children}</div>
    </aside>
  );
}

export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-950/70 px-2 py-2">
      <dt className="text-[9px] uppercase tracking-[0.16em] text-white/35">{label}</dt>
      <dd className="mt-0.5 text-xs tabular-nums text-white/90">{value}</dd>
    </div>
  );
}

export function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-white/40">{label}</dt>
      <dd className="truncate text-right tabular-nums text-white/85">{value}</dd>
    </div>
  );
}
