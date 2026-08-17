/** Screen placement of the 0–1 overlay (after pan, zoom, and overlay-radius). */
export type OverlayView = {
  left: number;
  top: number;
  width: number;
  height: number;
  fit: number;
};

export const EMPTY_VIEW: OverlayView = { left: 0, top: 0, width: 0, height: 0, fit: 1 };

export function overlayToScreen(x: number, y: number, view: OverlayView): [number, number] {
  return [
    view.left + (0.5 + (x - 0.5) * view.fit) * view.width,
    view.top + (0.5 + (y - 0.5) * view.fit) * view.height,
  ];
}

export function overlayCenter(view: OverlayView): [number, number] {
  return [view.left + view.width * 0.5, view.top + view.height * 0.5];
}

export function overlayRadiusPx(view: OverlayView): number {
  return (Math.max(view.width, view.height) / 2) * view.fit;
}

export function canvasDpr(w: number, h: number) {
  return Math.min(window.devicePixelRatio || 1, 2, 8192 / Math.max(w, 1), 8192 / Math.max(h, 1));
}
