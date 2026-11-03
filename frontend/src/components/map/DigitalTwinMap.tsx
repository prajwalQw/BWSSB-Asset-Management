import React, { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { SelectedAsset } from '../../types';
import { BasemapTheme } from '../../map/theme';
import { createCompositeBasemapStyle, switchBasemapTheme } from '../../map/basemap';
import { buildDeckLayers } from '../../map/deckOverlay';
import { LOD_CONFIG, CameraShortcut } from '../../map/lodConfig';
import { MapLegend } from './MapLegend';
import { 
  Sun, 
  Moon, 
  Globe, 
  Layers, 
  AlertTriangle, 
  X,
  Compass,
  Maximize2,
  Plus,
  Minus,
  Info
} from 'lucide-react';
import { useTwinStore } from '../../store/useTwinStore';

interface DigitalTwinMapProps {
  activeModule?: 'GIS' | 'IOT';
  onSelectAsset: (asset: SelectedAsset | null) => void;
  selectedAsset: SelectedAsset | null;
  activeScenario: string;
  currentHour: number;
  isDarkTheme: boolean;
  activeLeakPipeId?: string;
  demoStatus?: any;
  flyToTarget?: [number, number] | null;
  onNavigateToMonitor?: () => void;
}

// Module-level network dataset cache to prevent re-fetching and flashing across tab switches
let globalNetworkDataCache: {
  mainsLines: any[];
  simZonePipes: any[];
  simZoneNodes: any[];
  pumpingStations: any[];
  stps: any[];
  borewells: any[];
  divisionBoundaries: any[];
  waterBodies: any[];
} | null = null;

export const DigitalTwinMap: React.FC<DigitalTwinMapProps> = ({
  activeModule = 'GIS',
  onSelectAsset,
  selectedAsset,
  activeScenario,
  currentHour,
  isDarkTheme,
  activeLeakPipeId,
  demoStatus,
  flyToTarget,
  onNavigateToMonitor,
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const currentTimeRef = useRef<number>(0);

  // Basemap & Camera State
  const [activeTheme, setActiveTheme] = useState<BasemapTheme>(isDarkTheme ? 'dark' : 'light');
  const [mapReady, setMapReady] = useState(false);
  const [basemapError, setBasemapError] = useState<string | null>(null);
  const [coords, setCoords] = useState({ lon: 77.5946, lat: 12.9716, zoom: 11.2 });

  // Network dataset cache for Deck.gl (instantly populated if already cached)
  const [networkData, setNetworkData] = useState<{
    mainsLines: any[];
    simZonePipes: any[];
    simZoneNodes: any[];
    pumpingStations: any[];
    stps: any[];
    borewells: any[];
    divisionBoundaries: any[];
    waterBodies: any[];
  }>(() => globalNetworkDataCache || {
    mainsLines: [],
    simZonePipes: [],
    simZoneNodes: [],
    pumpingStations: [],
    stps: [],
    borewells: [],
    divisionBoundaries: [],
    waterBodies: [],
  });

  const { theme: storeTheme, isLegendOpen, setIsLegendOpen, flyToTarget: storeFlyToTarget } = useTwinStore();

  // Keep internal theme in sync with global store
  useEffect(() => {
    setActiveTheme(storeTheme);
    if (mapRef.current && mapReady) {
      switchBasemapTheme(mapRef.current, storeTheme);
    }
  }, [storeTheme, mapReady]);

  // Camera flyTo listener for zooming into exact leak location
  useEffect(() => {
    const target = flyToTarget || storeFlyToTarget;
    if (mapRef.current && mapReady && target && Array.isArray(target) && target.length === 2) {
      mapRef.current.flyTo({
        center: target as [number, number],
        zoom: 15.5,
        pitch: 45,
        bearing: -15,
        duration: 1800,
        essential: true,
      });
    }
  }, [flyToTarget, storeFlyToTarget, mapReady]);

  // Resilient dataset loader: attempts live API first with 2.5s timeout, falls back to bundled static GeoJSON
  useEffect(() => {
    let isCancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const fetchResource = async (apiUrl: string, fallbackUrl?: string) => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2500);
        const r = await fetch(apiUrl, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (r.ok) {
          const data = await r.json();
          if (data && Array.isArray(data.features) && data.features.length > 0) {
            return data;
          }
        }
      } catch {
        // proceed immediately to fallback if API is unreachable, offline, or times out
      }
      if (fallbackUrl) {
        try {
          const fb = await fetch(fallbackUrl);
          if (fb.ok) {
            const data = await fb.json();
            if (data && Array.isArray(data.features) && data.features.length > 0) {
              return data;
            }
          }
        } catch {
          // ignore fallback error
        }
      }
      return { features: [] };
    };

    const apiHost = '/api/v1';

    const loadDatasets = async (attempt = 1) => {
      try {
        const [
          mainsRes,
          zoneRes,
          psRes,
          stpRes,
          divRes,
          lakesRes,
        ] = await Promise.all([
          fetchResource(`${apiHost}/assets/water-lines-mains`, '/data/fallback/water_lines_gt_300mm.geojson'),
          fetchResource(`${apiHost}/hydraulics/zone`, '/data/fallback/simulated_zone.geojson'),
          fetchResource(`${apiHost}/assets/pumping-stations`, '/data/fallback/pumping_stations.geojson'),
          fetchResource(`${apiHost}/assets/stps`, '/data/fallback/stps.geojson'),
          fetchResource(`${apiHost}/assets/divisions`, '/data/fallback/division_boundaries.geojson'),
          fetchResource(`${apiHost}/water-bodies`),
        ]);

        if (isCancelled) return;

        const zoneFeatures = zoneRes.features || [];
        const simZonePipes = zoneFeatures.filter((f: any) => f.geometry?.type === 'LineString');
        const simZoneNodes = zoneFeatures.filter((f: any) => f.geometry?.type === 'Point');

        const mainsLines = mainsRes.features || [];
        const pumpingStations = psRes.features || [];
        const stps = stpRes.features || [];
        const divisionBoundaries = divRes.features || [];
        const waterBodies = lakesRes.features || [];

        const loaded = {
          mainsLines,
          simZonePipes,
          simZoneNodes,
          pumpingStations,
          stps,
          borewells: [],
          divisionBoundaries,
          waterBodies,
        };

        globalNetworkDataCache = loaded;
        setNetworkData(loaded);

        // If all assets came back empty because backend is still booting, retry in 3s
        if (pumpingStations.length === 0 && mainsLines.length === 0 && attempt < 4) {
          retryTimer = setTimeout(() => {
            if (!isCancelled) loadDatasets(attempt + 1);
          }, 3000);
        }
      } catch (err) {
        console.warn('Dataset loading warning:', err);
      }
    };

    // If cache already has network data, no need to show empty map while revalidating
    loadDatasets();

    return () => {
      isCancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [activeScenario]);

  // Initialize MapLibre ONCE with composite style & isolated Deck.gl MapboxOverlay
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const compositeStyle = createCompositeBasemapStyle();

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: compositeStyle,
      center: [77.5946, 12.9716],
      zoom: 11.2,
      pitch: 30,
      bearing: 0,
      maxPitch: 85,
    });

    // Navigation and Scale Controls
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    // Handle missing style images (e.g. wood-pattern in OSM Landuse styles) to suppress console warnings
    map.on('styleimagemissing', (e: any) => {
      const id = e.id;
      if (!map.hasImage(id)) {
        map.addImage(id, {
          width: 1,
          height: 1,
          data: new Uint8Array([0, 0, 0, 0]),
        });
      }
    });

    // Error handler for basemap tiles
    map.on('error', (e: any) => {
      const msg = e?.error?.message || '';
      if (msg.includes('tile') || msg.includes('404') || msg.includes('fetch')) {
        setBasemapError('Basemap tiles unavailable, using plain background with local vectors');
      }
    });

    // Create Deck.gl overlay with interleaved: false (separate WebGL canvas)
    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
    });
    map.addControl(overlay as any);
    overlayRef.current = overlay;

    // Movement listener for coordinate badge
    map.on('move', () => {
      const center = map.getCenter();
      setCoords({
        lon: Number(center.lng.toFixed(4)),
        lat: Number(center.lat.toFixed(4)),
        zoom: Number(map.getZoom().toFixed(1)),
      });
    });

    // Wait for style.load before signalling mapReady
    map.once('style.load', () => {
      setMapReady(true);
      switchBasemapTheme(map, activeTheme);
    });

    mapRef.current = map;

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (overlayRef.current) {
        map.removeControl(overlayRef.current as any);
        overlayRef.current = null;
      }
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Theme Switching: Update visibility and paint properties without EVER calling map.setStyle()
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    switchBasemapTheme(map, activeTheme);
  }, [activeTheme, mapReady]);

  // Handle fly-to targets
  useEffect(() => {
    if (!flyToTarget || !mapRef.current) return;
    mapRef.current.flyTo({
      center: flyToTarget,
      zoom: 16.0,
      pitch: 45,
      bearing: -15,
      duration: 1400,
      essential: true,
    });
  }, [flyToTarget]);

  // Fly-to helper for shortcuts
  const handleFlyToShortcut = (shortcut: CameraShortcut) => {
    if (!mapRef.current) return;
    mapRef.current.flyTo({
      center: shortcut.center,
      zoom: shortcut.zoom,
      pitch: shortcut.pitch,
      bearing: shortcut.bearing,
      duration: 1300,
      essential: true,
    });
  };

  // Render & Animation Loop for Deck.gl layers
  const renderDeckLayers = useCallback(() => {
    if (!overlayRef.current || !mapReady) return;

    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isHidden = typeof document !== 'undefined' && document.hidden;
    const isPaused = isHidden || prefersReducedMotion || coords.zoom < LOD_CONFIG.zoomThresholds.trunkMainsMinZoom;

    // 1 Hz impeller rotation two-frame swap
    const impellerFrame = Math.floor(Date.now() / 500) % 2;

    const layers = buildDeckLayers({
      activeModule,
      theme: activeTheme,
      zoom: coords.zoom,
      currentTime: currentTimeRef.current,
      impellerFrame,
      isAnimationPaused: isPaused,
      selectedAsset,
      activeLeakPipeId,
      demoStatus,
      onSelectAsset,
      onNavigateToMonitor,
      networkData,
    });

    overlayRef.current.setProps({ layers });
  }, [
    activeModule,
    activeTheme,
    coords.zoom,
    selectedAsset,
    activeLeakPipeId,
    demoStatus,
    onSelectAsset,
    onNavigateToMonitor,
    networkData,
    mapReady,
  ]);

  // Throttled continuous animation frame loop (capped at ~30 FPS for optimal performance and no lag)
  useEffect(() => {
    if (!mapReady) return;

    let lastTime = performance.now();
    let lastRenderTime = 0;
    const FRAME_INTERVAL_MS = 33.3; // ~30 fps cap for smooth performance without GPU overhead

    const animate = (now: number) => {
      const dt = (now - lastTime) / 1000;
      lastTime = now;

      currentTimeRef.current += dt * 25; // animation clock speed

      if (now - lastRenderTime >= FRAME_INTERVAL_MS) {
        lastRenderTime = now;
        renderDeckLayers();
      }

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [mapReady, renderDeckLayers]);

  return (
    <div className="w-full h-full relative overflow-hidden select-none">
      {/* MapLibre WebGL container */}
      <div ref={mapContainer} className="w-full h-full" />

      {/* Dismissible Error Toast */}
      {basemapError && (
        <div className="absolute top-4 left-4 z-30 max-w-md p-3 rounded-xl bg-amber-950/90 border border-amber-800 text-amber-200 text-xs backdrop-blur-md shadow-2xl flex items-start gap-2 animate-in fade-in slide-in-from-top-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block font-mono">Basemap Notice</span>
            <span className="text-[11px] leading-relaxed">{basemapError}</span>
          </div>
          <button
            onClick={() => setBasemapError(null)}
            className="p-1 rounded text-amber-400 hover:text-white hover:bg-amber-900 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Floating Controls Only: Zoom In/Out, Compass, Legend Toggle */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1.5">
        <button
          type="button"
          onClick={() => mapRef.current?.zoomIn()}
          className="w-8 h-8 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-md text-slate-700 dark:text-slate-300 flex items-center justify-center hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Zoom In"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => mapRef.current?.zoomOut()}
          className="w-8 h-8 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-md text-slate-700 dark:text-slate-300 flex items-center justify-center hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Zoom Out"
        >
          <Minus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => mapRef.current?.resetNorthPitch()}
          className="w-8 h-8 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-md text-slate-700 dark:text-slate-300 flex items-center justify-center hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Reset North / Bearing"
        >
          <Compass className="w-4 h-4 text-sky-500" />
        </button>
        <button
          type="button"
          onClick={() => setIsLegendOpen(!isLegendOpen)}
          className={`w-8 h-8 rounded-lg border shadow-md flex items-center justify-center transition-colors ${
            isLegendOpen
              ? 'bg-sky-600 text-white border-sky-600'
              : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
          title="Toggle Symbology Legend"
        >
          <Info className="w-4 h-4" />
        </button>
      </div>

      {/* Floating P&ID Symbology Legend Modal / Overlay */}
      {isLegendOpen && (
        <div className="absolute bottom-10 left-4 z-20 max-w-sm">
          <MapLegend theme={activeTheme} onClose={() => setIsLegendOpen(false)} />
        </div>
      )}

      {/* Bottom Right: Coordinate, Zoom, and Engine Badge */}
      <div className="absolute bottom-4 right-4 z-20 px-3 py-1 rounded-lg bg-white/90 dark:bg-slate-900/90 border border-slate-200 dark:border-slate-800 text-[10px] font-mono text-slate-600 dark:text-slate-400 backdrop-blur-md shadow-md flex items-center gap-2">
        <span>z: <strong className="text-sky-600 dark:text-sky-400">{coords.zoom}</strong></span>
        <span>•</span>
        <span>{coords.lat}&deg;N, {coords.lon}&deg;E</span>
        <span>•</span>
        <span className="text-emerald-600 dark:text-emerald-400 font-medium">MapLibre + Deck.gl</span>
      </div>
    </div>
  );
};
export default DigitalTwinMap;
