/** Simulated ATC radar: ITU/ICAO timing, mechanical sweep, and phosphor paint. */

export const C_KM_S = 299_792.458;
export const NM_KM = 1.852;
/** Round-trip microseconds per nautical mile (the radar mile). */
export const US_PER_NM_RT = 12.36;
/** ICAO Mode A/C/S transponder turnaround. */
export const SSR_TRANSPONDER_US = 3.0;

/** En-route SSR ~4.8 RPM → ~12.5 s/rev. */
export const SSR_RPM = 4.8;
/** Terminal PSR ~13 RPM → ~4.6 s/rev. */
export const PSR_RPM = 13;

export const SSR_PERIOD_S = 60 / SSR_RPM;
export const PSR_PERIOD_S = 60 / PSR_RPM;

export const SSR_COLOR = "rgba(103,232,249,0.92)";
export const PSR_COLOR = "rgba(134,239,172,0.92)";

export function rpmToPeriod(rpm: number) {
  return 60 / Math.max(rpm, 0.1);
}

export function sweepAzimuth(nowMs: number, periodS: number) {
  return ((nowMs / 1000 / periodS) * 360 + 360) % 360;
}

/** PSR echo: out and back at c. */
export function psrRoundTripUs(rangeKm: number) {
  return ((2 * Math.max(rangeKm, 0)) / C_KM_S) * 1e6;
}

/** SSR: echo plus mandatory 3.0 µs transponder delay. */
export function ssrRoundTripUs(rangeKm: number) {
  return psrRoundTripUs(rangeKm) + SSR_TRANSPONDER_US;
}

export function rangeNm(rangeKm: number) {
  return Math.max(rangeKm, 0) / NM_KM;
}

/** Range a station would compute from SSR time if it subtracts the 3 µs delay. */
export function ssrCorrectedNm(rangeKm: number) {
  return (ssrRoundTripUs(rangeKm) - SSR_TRANSPONDER_US) / US_PER_NM_RT;
}

/** If the 3 µs delay is not subtracted, the target appears ~0.24 NM farther. */
export function ssrUncorrectedNm(rangeKm: number) {
  return ssrRoundTripUs(rangeKm) / US_PER_NM_RT;
}

/** Two-way path: PSR ~ 1/R^4, SSR (transponder) ~ 1/R^2. */
export function psrEcho(rangeKm: number) {
  const r = Math.max(rangeKm, 1);
  return Math.min(1, (12 / r) ** 4);
}

export function ssrEcho(rangeKm: number) {
  const r = Math.max(rangeKm, 1);
  return Math.min(1, (18 / r) ** 2);
}

export function angleDelta(fromDeg: number, toDeg: number) {
  return ((toDeg - fromDeg + 540) % 360) - 180;
}

export function sweepCrossed(prevAz: number, nextAz: number, targetAz: number) {
  const step = (angleDelta(prevAz, nextAz) + 360) % 360;
  if (step <= 0 || step > 40) return false;
  const d0 = (angleDelta(prevAz, targetAz) + 360) % 360;
  return d0 >= 0 && d0 <= step;
}

export function kmhToKt(kmh?: number) {
  if (kmh == null || !Number.isFinite(kmh)) return null;
  return kmh / 1.852;
}

export function altMToFl(altM?: number) {
  if (altM == null || !Number.isFinite(altM)) return null;
  return Math.round((altM * 3.28084) / 100);
}

export function vrateLetter(vrateMs?: number) {
  if (vrateMs == null || !Number.isFinite(vrateMs)) return "L";
  if (vrateMs > 1.5) return "C";
  if (vrateMs < -1.5) return "D";
  return "L";
}
