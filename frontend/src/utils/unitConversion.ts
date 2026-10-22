/**
 * Canonical Unit Conversion Utilities for BWSSB Digital Twin.
 * Standard conversions:
 * - L/s -> m3/h: m3/h = L/s * 3.6
 * - m3/h -> MLD: MLD = (m3/h * 24) / 1000
 * - L/s -> MLD: MLD = (L/s * 3.6 * 24) / 1000 = L/s * 0.0864
 */

export function lpsToM3h(lps: number): number {
  return lps * 3.6;
}

export function m3hToMld(m3h: number): number {
  return (m3h * 24) / 1000;
}

export function lpsToMld(lps: number): number {
  return m3hToMld(lpsToM3h(lps));
}

export function mldToLps(mld: number): number {
  return (mld * 1000) / (24 * 3.6);
}

export function mldToM3h(mld: number): number {
  return (mld * 1000) / 24;
}
