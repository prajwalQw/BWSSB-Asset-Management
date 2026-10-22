/**
 * Map Engine Theme Design Tokens
 * Per-theme tokens for basemap, pipe core/casing, labels, icons, flow particles, and status colors.
 */

export type BasemapTheme = 'dark' | 'light' | 'satellite' | 'grayscale';

export type AssetStatus = 'NORMAL' | 'WATCH' | 'ALERT' | 'NODATA';
export type DataTier = 'REAL' | 'SIMULATED' | 'LIVE';

export interface ThemeTokens {
  id: BasemapTheme;
  name: string;
  backgroundColor: string;
  pipeCasing: [number, number, number, number];
  pipeCoreNormal: [number, number, number, number];
  pipeCoreWatch: [number, number, number, number];
  pipeCoreAlert: [number, number, number, number];
  sewerLine: [number, number, number, number];
  waterBodiesFill: string;
  waterBodiesOutline: string;
  flowParticle: [number, number, number, number];
  labelColor: string;
  labelHalo: string;
  iconOutline: [number, number, number, number];
  divisionBoundary: string;
}

export const MAP_THEMES: Record<BasemapTheme, ThemeTokens> = {
  dark: {
    id: 'dark',
    name: 'Dark Vector',
    backgroundColor: '#090d16',
    pipeCasing: [2, 6, 23, 230], // #020617
    pipeCoreNormal: [6, 182, 212, 240], // vibrant cyan #06b6d4
    pipeCoreWatch: [245, 158, 11, 250], // amber #f59e0b
    pipeCoreAlert: [239, 68, 68, 255], // red #ef4444
    sewerLine: [140, 115, 65, 200], // olive-brown
    waterBodiesFill: '#0f2942', // Calm muted blue
    waterBodiesOutline: '#1e3a5f',
    flowParticle: [255, 255, 255, 230],
    labelColor: '#e2e8f0',
    labelHalo: '#020617',
    iconOutline: [2, 6, 23, 255],
    divisionBoundary: '#334155',
  },
  light: {
    id: 'light',
    name: 'Light Vector',
    backgroundColor: '#f8fafc',
    pipeCasing: [15, 23, 42, 220], // dark slate casing for contrast on light basemap
    pipeCoreNormal: [2, 132, 199, 250], // #0284c7
    pipeCoreWatch: [217, 119, 6, 255], // #d97706
    pipeCoreAlert: [220, 38, 38, 255], // #dc2626
    sewerLine: [120, 100, 55, 220], // olive-brown
    waterBodiesFill: '#cbd5e1', // soft calm slate-blue
    waterBodiesOutline: '#94a3b8',
    flowParticle: [2, 132, 199, 255],
    labelColor: '#0f172a',
    labelHalo: '#ffffff',
    iconOutline: [255, 255, 255, 255],
    divisionBoundary: '#94a3b8',
  },
  satellite: {
    id: 'satellite',
    name: 'Hybrid Satellite',
    backgroundColor: '#05070a',
    pipeCasing: [255, 255, 255, 230], // White casing for maximum contrast over dark aerial satellite imagery
    pipeCoreNormal: [0, 180, 216, 255], // #00b4d8
    pipeCoreWatch: [251, 191, 36, 255], // #fbbf24
    pipeCoreAlert: [248, 113, 113, 255], // #f87171
    sewerLine: [180, 150, 90, 230],
    waterBodiesFill: 'rgba(2, 132, 199, 0.35)',
    waterBodiesOutline: '#38bdf8',
    flowParticle: [255, 255, 255, 255],
    labelColor: '#ffffff',
    labelHalo: '#000000',
    iconOutline: [0, 0, 0, 255],
    divisionBoundary: '#e2e8f0',
  },
  grayscale: {
    id: 'grayscale',
    name: 'Monochrome Gray',
    backgroundColor: '#18181b',
    pipeCasing: [9, 9, 11, 240],
    pipeCoreNormal: [56, 189, 248, 240],
    pipeCoreWatch: [245, 158, 11, 250],
    pipeCoreAlert: [239, 68, 68, 255],
    sewerLine: [130, 110, 60, 210],
    waterBodiesFill: '#27272a',
    waterBodiesOutline: '#3f3f46',
    flowParticle: [255, 255, 255, 240],
    labelColor: '#f4f4f5',
    labelHalo: '#09090b',
    iconOutline: [9, 9, 11, 255],
    divisionBoundary: '#52525b',
  },
};

export const STATUS_COLORS: Record<AssetStatus, [number, number, number, number]> = {
  NORMAL: [16, 185, 129, 255], // Green #10b981
  WATCH: [245, 158, 11, 255], // Amber #f59e0b
  ALERT: [239, 68, 68, 255], // Red #ef4444
  NODATA: [148, 163, 184, 255], // Slate #94a3b8
};

export const DATA_TIER_COLORS: Record<DataTier, [number, number, number, number]> = {
  REAL: [14, 165, 233, 255], // Cyan #0ea5e9
  SIMULATED: [168, 85, 247, 255], // Purple #a855f7
  LIVE: [16, 185, 129, 255], // Green #10b981
};
