/**
 * Deck.gl Overlay Engine for Digital Twin
 *
 * Implements:
 * - MapboxOverlay with interleaved: false (isolated WebGL canvas)
 * - Two-pass pipe rendering: Casing (PathLayer) under Core (PathLayer)
 * - Dynamic TripsLayer flow animation with velocity-scaled timestamps
 * - Static direction chevrons at z >= 15
 * - Full P&ID ISA-5.1 Icon Symbology with status rings and data tier badges
 * - Level of Detail (LOD) zoom transitions (z < 11, 11-13, 14-16, >= 17)
 * - High-zoom Site-Plan view at z >= 17: footprint polygons, manifolds, pump units,
 *   valves, meters, instrument tags, and 1 Hz rotating impeller glyphs
 */

import { PathLayer, IconLayer, TextLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import { BasemapTheme, MAP_THEMES, STATUS_COLORS, DATA_TIER_COLORS, AssetStatus, DataTier } from './theme';
import { LOD_CONFIG } from './lodConfig';
import { alongLine, offsetMetersToLngLat, getBearing } from './turfMath';
import { buildIconAtlas, IconBounds } from './icons';
import { SelectedAsset } from '../types';
import { layerRegistry } from '../features/iot/registry/layerRegistry';

export interface DeckOverlayProps {
  activeModule?: 'GIS' | 'IOT';
  theme: BasemapTheme;
  zoom: number;
  currentTime: number;
  impellerFrame: number;
  isAnimationPaused: boolean;
  selectedAsset: SelectedAsset | null;
  activeLeakPipeId?: string;
  demoStatus?: any;
  onSelectAsset: (asset: SelectedAsset) => void;
  onNavigateToMonitor?: () => void;
  networkData: {
    mainsLines: any[];
    simZonePipes: any[];
    simZoneNodes: any[];
    pumpingStations: any[];
    stps: any[];
    borewells: any[];
    divisionBoundaries: any[];
    waterBodies: any[];
  };
}

let cachedAtlas: {
  atlasUrl: string;
  atlasImage: HTMLCanvasElement;
  mapping: Record<string, IconBounds>;
} | null = null;

function getAtlas() {
  if (!cachedAtlas && typeof document !== 'undefined') {
    cachedAtlas = buildIconAtlas();
  }
  return cachedAtlas;
}

// Module-level caches for geometry to prevent allocating thousands of objects every animation frame
let cachedRawPipesRef: any[] | null = null;
let cachedFlatPipes: FlatPipeSegment[] = [];
let cachedTripsRef: FlatPipeSegment[] | null = null;
let cachedTripsData: any[] = [];

export interface FlatPipeSegment {
  id: string;
  properties: any;
  path: [number, number][];
}

/**
 * Safely flattens MultiLineString and LineString features into uniform 2D path segments,
 * preventing nested array coordinate errors in Deck.gl attribute buffers.
 */
function flattenPipes(features: any[]): FlatPipeSegment[] {
  const segments: FlatPipeSegment[] = [];
  for (const f of features) {
    if (!f || !f.geometry || !f.geometry.coordinates) continue;
    const props = f.properties || {};
    const baseId = props.id || 'pipe';
    const type = f.geometry.type;

    if (type === 'LineString') {
      const coords = f.geometry.coordinates;
      if (Array.isArray(coords) && coords.length >= 2 && Array.isArray(coords[0]) && typeof coords[0][0] === 'number') {
        segments.push({
          id: baseId,
          properties: props,
          path: coords as [number, number][],
        });
      }
    } else if (type === 'MultiLineString') {
      const lines = f.geometry.coordinates;
      if (Array.isArray(lines)) {
        lines.forEach((line: any, idx: number) => {
          if (Array.isArray(line) && line.length >= 2 && Array.isArray(line[0]) && typeof line[0][0] === 'number') {
            segments.push({
              id: `${baseId}-${idx}`,
              properties: props,
              path: line as [number, number][],
            });
          }
        });
      }
    }
  }
  return segments;
}

/**
 * Builds the complete array of Deck.gl layers according to current zoom LOD and theme.
 */
export function buildDeckLayers(props: DeckOverlayProps) {
  const {
    theme,
    zoom,
    currentTime,
    impellerFrame,
    isAnimationPaused,
    selectedAsset,
    activeLeakPipeId,
    onSelectAsset,
    networkData,
  } = props;

  const tokens = MAP_THEMES[theme];
  const atlas = getAtlas();
  const layers: any[] = [];

  const lod = LOD_CONFIG.zoomThresholds;

  // ---------------------------------------------------------------------------
  // 1. Water Bodies Polygons (Calm blue, calm contrast)
  // ---------------------------------------------------------------------------
  if (networkData.waterBodies && networkData.waterBodies.length > 0) {
    layers.push(
      new PolygonLayer({
        id: 'water-bodies-layer',
        data: networkData.waterBodies,
        getPolygon: (d: any) => d.geometry.coordinates,
        getFillColor: () => [15, 41, 66, theme === 'dark' ? 180 : 120],
        getLineColor: () => [30, 58, 95, 220],
        getLineWidth: 1.5,
        lineWidthUnits: 'pixels',
        pickable: true,
        onClick: (info: any) => {
          if (info.object) {
            onSelectAsset({
              id: info.object.properties?.id || 'WATER_BODY',
              name: info.object.properties?.name || 'Bengaluru Lake / Reservoir',
              category: 'WATER_BODY',
              dataTier: 'REAL',
              source: 'Verified Water Resource',
              date: '2026-10-21',
              coordinates: info.coordinate ? [info.coordinate[0], info.coordinate[1]] : undefined,
              properties: info.object.properties || {},
            });
          }
        },
      })
    );
  }

  // ---------------------------------------------------------------------------
  // 2. Division Boundary Polygons & Supercluster Centroid Labels (z < 11)
  // ---------------------------------------------------------------------------
  if (networkData.divisionBoundaries && networkData.divisionBoundaries.length > 0) {
    layers.push(
      new PathLayer({
        id: 'division-boundaries-path',
        data: networkData.divisionBoundaries,
        getPath: (d: any) => d.geometry.coordinates,
        getColor: () => (theme === 'light' ? [148, 163, 184, 180] : [71, 85, 105, 180]),
        getWidth: 1.5,
        widthUnits: 'pixels',
        dashJustified: true,
      })
    );

    if (zoom < lod.trunkMainsMinZoom) {
      layers.push(
        new TextLayer({
          id: 'division-cluster-labels',
          data: networkData.divisionBoundaries,
          getPosition: (d: any) => d.properties?.centroid || [77.5946, 12.9716],
          getText: (d: any) =>
            `${d.properties?.DivisionName || 'Division'}\n(${d.properties?.asset_count || '1.4k'} assets)`,
          getSize: 12,
          getColor: () => (theme === 'light' ? [15, 23, 42, 255] : [241, 245, 249, 255]),
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'center',
          fontFamily: 'monospace',
          outlineWidth: 3,
          outlineColor: theme === 'light' ? [255, 255, 255, 255] : [2, 6, 23, 255],
          fontSettings: { sdf: true },
        })
      );
    }
  }

  // Combine transmission and simulated zone pipes with memoized flattening
  const rawMains = networkData.mainsLines || [];
  const rawSim = networkData.simZonePipes || [];
  if (cachedRawPipesRef !== rawMains) {
    cachedRawPipesRef = rawMains;
    cachedFlatPipes = flattenPipes([...rawMains, ...rawSim]);
    cachedTripsRef = null; // Invalidate trips cache when underlying data changes
  }
  const allFlatPipes = cachedFlatPipes;

  // Filter pipes by diameter class based on Zoom LOD
  const visiblePipes = allFlatPipes.filter((p) => {
    const diam = p.properties?.diameter_mm || 400;
    if (zoom < lod.trunkMainsMinZoom) {
      return diam >= LOD_CONFIG.pipeClasses.trunk.minDiameterMm;
    }
    if (zoom < lod.allMainsMinZoom) {
      return diam >= LOD_CONFIG.pipeClasses.mains.minDiameterMm;
    }
    return true;
  });

  // ---------------------------------------------------------------------------
  // 3. Two-Pass Pipe Styling: PASS 1 - WIDER CASING (PathLayer)
  // ---------------------------------------------------------------------------
  if (visiblePipes.length > 0) {
    const demoState = props.demoStatus?.state || 'IDLE';
    const isLeakingPhase = Boolean(props.demoStatus && props.demoStatus.state !== 'IDLE' && props.demoStatus.state !== 'RESTORED');
    const isIsolatedPhase = ['ISOLATING', 'ISOLATED'].includes(demoState);

    const isDemoCorridor = (pipeId?: string) => {
      if (!pipeId) return false;
      const norm = String(pipeId).toUpperCase();
      return (
        norm === 'CORR_TATAGUNI_MOUNT_JOY' ||
        norm === 'CORR_TG_MJ' ||
        pipeId === activeLeakPipeId ||
        (norm.includes('TATAGUNI') && norm.includes('MOUNT_JOY')) ||
        norm === 'PIPE_CORRIDOR_01'
      );
    };

    layers.push(
      new PathLayer({
        id: 'pipes-casing-layer',
        data: visiblePipes,
        opacity: props.activeModule === 'IOT' ? 0.35 : 1.0,
        getPath: (d: FlatPipeSegment) => d.path,
        getColor: (d: FlatPipeSegment) => {
          const isSelected = selectedAsset && (selectedAsset.id === d.properties?.id || selectedAsset.id === d.id);
          const isSuspect = activeLeakPipeId && (activeLeakPipeId === d.properties?.id || activeLeakPipeId === d.id);
          const isCorr = isDemoCorridor(d.properties?.id || d.id);
          if (isCorr && isLeakingPhase) return [239, 68, 68, 255]; // Red leaked pipe during demo until repair done
          if (isSelected || isSuspect) return [239, 68, 68, 255]; // Red highlight casing
          return tokens.pipeCasing;
        },
        getWidth: (d: FlatPipeSegment) => {
          const isCorr = isDemoCorridor(d.properties?.id || d.id);
          if (isCorr && isLeakingPhase) return 18.0; // Thicker casing for prominent visual
          const diam = d.properties?.diameter_mm || 350;
          if (diam >= 600) return LOD_CONFIG.pipeClasses.trunk.casingWidthMeters;
          if (diam >= 300) return LOD_CONFIG.pipeClasses.mains.casingWidthMeters;
          return LOD_CONFIG.pipeClasses.distribution.casingWidthMeters;
        },
        widthUnits: 'meters',
        widthMinPixels: 3.5,
        widthMaxPixels: 18.0,
        capRounded: true,
        jointRounded: true,
      })
    );

    // ---------------------------------------------------------------------------
    // 4. Two-Pass Pipe Styling: PASS 2 - NARROWER CORE (PathLayer)
    // ---------------------------------------------------------------------------
    layers.push(
      new PathLayer({
        id: 'pipes-core-layer',
        data: visiblePipes,
        opacity: props.activeModule === 'IOT' ? 0.35 : 1.0,
        getPath: (d: FlatPipeSegment) => d.path,
        getColor: (d: FlatPipeSegment) => {
          const isCorr = isDemoCorridor(d.properties?.id || d.id);
          if (isCorr && isLeakingPhase) return [255, 30, 60, 255]; // Vivid red leaked pipe core
          const status = (d.properties?.status || 'NORMAL') as AssetStatus;
          if (status === 'ALERT' || status === ('BURST' as any) || status === ('LEAK_SUSPECTED' as any)) {
            return tokens.pipeCoreAlert;
          }
          if (status === 'WATCH' || status === ('PRESSURE_DEFICIT' as any)) {
            return tokens.pipeCoreWatch;
          }
          return tokens.pipeCoreNormal;
        },
        getWidth: (d: FlatPipeSegment) => {
          const diam = d.properties?.diameter_mm || 350;
          if (diam >= 600) return LOD_CONFIG.pipeClasses.trunk.coreWidthMeters;
          if (diam >= 300) return LOD_CONFIG.pipeClasses.mains.coreWidthMeters;
          return LOD_CONFIG.pipeClasses.distribution.coreWidthMeters;
        },
        widthUnits: 'meters',
        widthMinPixels: 2.0,
        widthMaxPixels: 9.0,
        capRounded: true,
        jointRounded: true,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 120],
        onClick: (info: any) => {
          if (info.object) {
            const props = info.object.properties || {};
            onSelectAsset({
              id: props.id || info.object.id || 'PIPE',
              name: props.name || `Water Pipe (${props.diameter_mm || 400}mm ${props.material || 'DI'})`,
              category: 'PIPE',
              dataTier: props._data_tier === 'SIMULATED' || props.is_simulated ? 'SIMULATED' : 'REAL',
              source: props._source || 'BWSSB Network Model',
              date: props._date || '2026-10-21',
              coordinates: info.coordinate ? [info.coordinate[0], info.coordinate[1]] : undefined,
              properties: props,
            });
          }
        },
      })
    );
  }

  // ---------------------------------------------------------------------------
  // 5. Flow Pulse Animation with TripsLayer
  // ---------------------------------------------------------------------------
  if (!isAnimationPaused && zoom >= lod.trunkMainsMinZoom && visiblePipes.length > 0) {
    const demoState = props.demoStatus?.state || 'IDLE';
    const isIsolatedPhase = ['ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING'].includes(demoState);
    const isDemoCorridor = (pipeId?: string) => {
      if (!pipeId) return false;
      const norm = String(pipeId).toUpperCase();
      return (
        norm === 'CORR_TATAGUNI_MOUNT_JOY' ||
        norm === 'CORR_TG_MJ' ||
        pipeId === activeLeakPipeId ||
        (norm.includes('TATAGUNI') && norm.includes('MOUNT_JOY')) ||
        norm === 'PIPE_CORRIDOR_01'
      );
    };

    // Generate clean paths with velocity timestamps (memoized across frames)
    if (cachedTripsRef !== visiblePipes) {
      cachedTripsRef = visiblePipes;
      cachedTripsData = visiblePipes
        .filter((p) => {
          if (!p.path || p.path.length < 2) return false;
          return true;
        })
        .map((p) => {
          const coords = p.path;
          const velocity = p.properties?.current_velocity_mps || LOD_CONFIG.flowAnimation.defaultVelocityMps;
          let cumulativeTime = 0;
          const cleanPath: [number, number][] = [];
          const timestamps: number[] = [];

          coords.forEach((pt, i) => {
            if (i > 0) {
              const segDist = alongLine([coords[i - 1], pt], 9999).coord;
              const dist = 50; // estimated segment meters
              cumulativeTime += dist / Math.max(0.5, velocity);
            }
            cleanPath.push([pt[0], pt[1]]);
            timestamps.push(cumulativeTime);
          });

          return {
            id: p.id,
            path: cleanPath,
            timestamps: timestamps,
          };
        });
    }

    const tripsData = isIsolatedPhase
      ? cachedTripsData.filter((t) => !isDemoCorridor(t.id))
      : cachedTripsData;

    layers.push(
      new TripsLayer({
        id: 'flow-trips-animation',
        data: tripsData,
        getPath: (d: any) => d.path,
        getTimestamps: (d: any) => d.timestamps,
        getColor: () => tokens.flowParticle,
        currentTime: currentTime % 600,
        trailLength: LOD_CONFIG.flowAnimation.trailLength,
        fadeTrail: LOD_CONFIG.flowAnimation.fadeTrail,
        widthUnits: 'pixels',
        getWidth: 2.5,
      })
    );
  }

  // ---------------------------------------------------------------------------
  // 5b. Demo Leak Markers: Uncertainty Halo, Closed Valve, Repair Marker
  // ---------------------------------------------------------------------------
  if (props.demoStatus && props.demoStatus.state !== 'IDLE' && props.demoStatus.state !== 'RESTORED') {
    const demoState = props.demoStatus.state;
    const isLeakingPhase = ['LEAK_INJECTED', 'DETECTED', 'AGENT_DIAGNOSED', 'AWAITING_APPROVAL', 'COUNTDOWN'].includes(demoState);
    const isIsolatedPhase = ['ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING'].includes(demoState);
    const leakCoords: [number, number] = props.demoStatus.config?.leak_coordinates || [77.5380, 12.9050];

    // Uncertainty halo layer at leak spot during leaking phase
    if (isLeakingPhase) {
      layers.push(
        new ScatterplotLayer({
          id: 'demo-leak-uncertainty-halo',
          data: [{ position: leakCoords }],
          getPosition: (d: any) => d.position,
          getRadius: () => 140,
          getFillColor: () => [244, 63, 94, 65],
          getLineColor: () => [244, 63, 94, 220],
          stroked: true,
          filled: true,
          lineWidthMinPixels: 2,
          radiusUnits: 'meters',
        })
      );
    }

    if (isIsolatedPhase) {
      // Closed valve icon / marker
      layers.push(
        new TextLayer({
          id: 'demo-valve-closed-marker',
          data: [{ position: [77.5725, 12.9360], text: '[VALVE BFV-104 CLOSED]' }],
          getPosition: (d: any) => d.position,
          getText: (d: any) => d.text,
          getSize: 12,
          getColor: () => [255, 255, 255, 255],
          background: true,
          getBackgroundColor: () => [30, 41, 59, 240],
          backgroundPadding: [6, 4],
          fontFamily: 'monospace',
          getTextAnchor: 'middle',
        })
      );

      // Repair marker
      if (demoState === 'REPAIR_DISPATCHED' || demoState === 'REPAIR_IN_PROGRESS') {
        layers.push(
          new TextLayer({
            id: 'demo-repair-wrench-marker',
            data: [{ position: leakCoords, text: '[REPAIR IN PROGRESS]' }],
            getPosition: (d: any) => d.position,
            getText: (d: any) => d.text,
            getSize: 12,
            getColor: () => [255, 255, 255, 255],
            background: true,
            getBackgroundColor: () => [2, 132, 199, 240],
            backgroundPadding: [6, 4],
            fontFamily: 'monospace',
            getTextAnchor: 'middle',
          })
        );
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 6. Direction Chevrons on Pipe Segments (z >= 15)
  // ---------------------------------------------------------------------------
  if (atlas && zoom >= lod.chevronsMinZoom && visiblePipes.length > 0) {
    const chevronPoints: any[] = [];
    visiblePipes.forEach((p) => {
      const coords = p.path;
      if (coords && coords.length >= 2) {
        const midIdx = Math.floor(coords.length / 2);
        const p1 = coords[Math.max(0, midIdx - 1)];
        const p2 = coords[midIdx];
        const bearing = getBearing(p1, p2);
        chevronPoints.push({
          coord: p2,
          angle: 360 - bearing, // IconLayer counter-clockwise
        });
      }
    });

    layers.push(
      new IconLayer({
        id: 'pipe-direction-chevrons',
        data: chevronPoints,
        iconAtlas: atlas.atlasUrl,
        iconMapping: atlas.mapping,
        getIcon: () => 'chevron',
        getPosition: (d: any) => d.coord,
        getSize: 14,
        getAngle: (d: any) => d.angle,
        sizeUnits: 'pixels',
        billboard: false,
      })
    );
  }

  // ---------------------------------------------------------------------------
  // 7. P&ID Station and Infrastructure Symbology (z >= 11)
  // ---------------------------------------------------------------------------
  if (atlas && zoom >= lod.trunkMainsMinZoom && props.activeModule !== 'IOT') {
    const assetItems: any[] = [];

    // Pumping Stations
    (networkData.pumpingStations || []).forEach((ps) => {
      assetItems.push({
        id: ps.properties?.id || ps.properties?.KGISPumpStationID || 'PS',
        name: ps.properties?.name || 'Pumping Station',
        type: 'pumping_station',
        coord: ps.geometry.coordinates,
        status: (ps.properties?.status || 'NORMAL') as AssetStatus,
        dataTier: (ps.properties?.data_tier || 'REAL') as DataTier,
        properties: ps.properties,
      });
    });

    // STPs
    (networkData.stps || []).forEach((stp) => {
      assetItems.push({
        id: stp.properties?.id || 'STP',
        name: stp.properties?.STPName || 'Sewage Treatment Plant',
        type: 'stp',
        coord: stp.geometry.coordinates,
        status: 'NORMAL' as AssetStatus,
        dataTier: 'REAL' as DataTier,
        properties: stp.properties,
      });
    });

    // Simulated Nodes (Tanks, Flow Meters, Valves, Borewells)
    (networkData.simZoneNodes || []).forEach((node) => {
      const elType = node.properties?.element_type;
      let iconType: any = 'flow_meter';
      if (elType === 'TANK_GLR' || elType === 'TANK_OHT' || elType === 'Tank') iconType = 'glr_tank';
      else if (elType === 'PUMPING_STATION') iconType = 'pumping_station';
      else if (elType === 'VALVE') iconType = node.properties?.is_closed ? 'valve_closed' : 'valve_open';
      else if (elType === 'PRESSURE_TRANSMITTER') iconType = 'pressure_transmitter';
      else if (elType === 'BOREWELL') iconType = 'borewell';

      assetItems.push({
        id: node.properties?.id || 'NODE',
        name: node.properties?.name || 'Network Node',
        type: iconType,
        coord: node.geometry.coordinates,
        status: (node.properties?.status || 'NORMAL') as AssetStatus,
        dataTier: (node.properties?._data_tier || 'SIMULATED') as DataTier,
        properties: node.properties,
      });
    });

    // P&ID Base Icon Layer
    layers.push(
      new IconLayer({
        id: 'pid-assets-icon-layer',
        data: assetItems,
        iconAtlas: atlas.atlasUrl,
        iconMapping: atlas.mapping,
        getIcon: (d: any) => d.type,
        getPosition: (d: any) => d.coord,
        getSize: zoom >= 15 ? 32 : 24,
        sizeUnits: 'pixels',
        pickable: true,
        autoHighlight: true,
        onClick: (info: any) => {
          if (info.object) {
            onSelectAsset({
              id: info.object.id,
              name: info.object.name,
              category: info.object.type.toUpperCase(),
              dataTier: info.object.dataTier,
              source: info.object.properties?._source || 'BWSSB Twin Asset Record',
              date: info.object.properties?._date || '2026-10-21',
              coordinates: info.object.coord,
              properties: info.object.properties || {},
            });
          }
        },
      })
    );

    // Collision-filtered Asset Labels (z >= 12.5)
    if (zoom >= 12.5) {
      layers.push(
        new TextLayer({
          id: 'pid-assets-text-labels',
          data: assetItems,
          getPosition: (d: any) => d.coord,
          getText: (d: any) => d.name,
          getSize: 11,
          getColor: () => (theme === 'light' ? [15, 23, 42, 255] : [241, 245, 249, 255]),
          getPixelOffset: [0, 22],
          getTextAnchor: 'middle',
          fontFamily: 'monospace',
          outlineWidth: 2.5,
          outlineColor: theme === 'light' ? [255, 255, 255, 255] : [2, 6, 23, 255],
          fontSettings: { sdf: true },
        })
      );
    }
  }

  // ---------------------------------------------------------------------------
  // 8. High-Zoom SITE-PLAN View (z >= 17)
  // ---------------------------------------------------------------------------
  if (atlas && zoom >= lod.sitePlanMinZoom && props.activeModule !== 'IOT') {
    const siteConfig = LOD_CONFIG.sitePlans.PS_TATAGUNI_TERMINAL;
    if (siteConfig) {
      const origin = siteConfig.origin;
      const rot = siteConfig.footprint.rotation_deg;

      // Footprint Polygon
      const halfW = siteConfig.footprint.width_m / 2;
      const halfL = siteConfig.footprint.length_m / 2;
      const footprintCorners = [
        offsetMetersToLngLat(origin, [-halfW, -halfL], rot),
        offsetMetersToLngLat(origin, [halfW, -halfL], rot),
        offsetMetersToLngLat(origin, [halfW, halfL], rot),
        offsetMetersToLngLat(origin, [-halfW, halfL], rot),
      ];

      layers.push(
        new PolygonLayer({
          id: 'site-plan-footprint',
          data: [{ polygon: footprintCorners }],
          getPolygon: (d: any) => d.polygon,
          getFillColor: () => [30, 41, 59, 120],
          getLineColor: () => [14, 165, 233, 240],
          getLineWidth: 2,
          lineWidthUnits: 'pixels',
        })
      );

      // Suction & Discharge Headers (Meters)
      const suctionHeaderPath = [
        offsetMetersToLngLat(origin, siteConfig.suction_header.offset_start_m, rot),
        offsetMetersToLngLat(origin, siteConfig.suction_header.offset_end_m, rot),
      ];
      const dischargeHeaderPath = [
        offsetMetersToLngLat(origin, siteConfig.discharge_header.offset_start_m, rot),
        offsetMetersToLngLat(origin, siteConfig.discharge_header.offset_end_m, rot),
      ];

      layers.push(
        new PathLayer({
          id: 'site-plan-headers',
          data: [
            { path: suctionHeaderPath, name: 'Suction Header (1200mm)' },
            { path: dischargeHeaderPath, name: 'Discharge Header (1000mm)' },
          ],
          getPath: (d: any) => d.path,
          getColor: () => [6, 182, 212, 240],
          getWidth: 6.0,
          widthUnits: 'meters',
        })
      );

      // Individual Pump Units in a row + 1 Hz Rotating Impeller Glyphs
      const demoStateForPump = props.demoStatus?.state || 'IDLE';
      const isIsolatedPumpPhase = ['ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING'].includes(demoStateForPump);
      const pumpUnitsData = siteConfig.pump_units.map((unit) => {
        const unitCoord = offsetMetersToLngLat(origin, unit.offset_m, rot);
        const suctionValveCoord = offsetMetersToLngLat(origin, unit.suction_valve_offset_m, rot);
        const dischargeValveCoord = offsetMetersToLngLat(origin, unit.discharge_valve_offset_m, rot);
        const isIsolated = isIsolatedPumpPhase && (unit.tag === 'P1' || unit.id === 'PUMP_TG_H1');

        return {
          ...unit,
          coord: unitCoord,
          suctionValveCoord,
          dischargeValveCoord,
          isIsolated,
          impellerIcon: isIsolated ? 'pump_unit' : (impellerFrame === 0 ? 'pump_impeller_0' : 'pump_impeller_1'),
        };
      });

      // Pump units
      layers.push(
        new IconLayer({
          id: 'site-plan-pump-units',
          data: pumpUnitsData,
          iconAtlas: atlas.atlasUrl,
          iconMapping: atlas.mapping,
          getIcon: () => 'pump_unit',
          getPosition: (d: any) => d.coord,
          getSize: 42,
          sizeUnits: 'pixels',
          pickable: true,
          onClick: (info: any) => {
            if (info.object) {
              onSelectAsset({
                id: info.object.id,
                name: info.object.tag,
                category: 'PUMP_UNIT',
                dataTier: 'SIMULATED',
                source: 'Tataguni Terminal SCADA Model',
                date: '2026-10-21',
                coordinates: info.object.coord,
                properties: {
                  rated_kw: info.object.rated_kw,
                  rated_current_a: info.object.rated_current_a,
                  rated_voltage_v: info.object.rated_voltage_v,
                  status: 'STEADY_RUNNING',
                },
              });
            }
          },
        })
      );

      // 1 Hz Rotating Impeller Glyphs
      layers.push(
        new IconLayer({
          id: 'site-plan-impellers',
          data: pumpUnitsData,
          iconAtlas: atlas.atlasUrl,
          iconMapping: atlas.mapping,
          getIcon: (d: any) => d.impellerIcon,
          getPosition: (d: any) => d.coord,
          getSize: 22,
          sizeUnits: 'pixels',
        })
      );

      // Discharge and Suction Valves
      const valvesData = pumpUnitsData.flatMap((u) => [
        { coord: u.suctionValveCoord, type: 'valve_open', tag: `${u.id} Suction Valve` },
        { coord: u.dischargeValveCoord, type: 'valve_open', tag: `${u.id} Discharge Valve` },
      ]);

      layers.push(
        new IconLayer({
          id: 'site-plan-valves',
          data: valvesData,
          iconAtlas: atlas.atlasUrl,
          iconMapping: atlas.mapping,
          getIcon: (d: any) => d.type,
          getPosition: (d: any) => d.coord,
          getSize: 20,
          sizeUnits: 'pixels',
        })
      );

      // Flow meter & Pressure transmitter
      const fmCoord = offsetMetersToLngLat(origin, siteConfig.instrumentation.flow_meter.offset_m, rot);
      const ptCoord = offsetMetersToLngLat(origin, siteConfig.instrumentation.pressure_transmitter.offset_m, rot);

      layers.push(
        new IconLayer({
          id: 'site-plan-instruments',
          data: [
            { coord: fmCoord, type: 'flow_meter', tag: siteConfig.instrumentation.flow_meter.tag },
            { coord: ptCoord, type: 'pressure_transmitter', tag: siteConfig.instrumentation.pressure_transmitter.tag },
          ],
          iconAtlas: atlas.atlasUrl,
          iconMapping: atlas.mapping,
          getIcon: (d: any) => d.type,
          getPosition: (d: any) => d.coord,
          getSize: 28,
          sizeUnits: 'pixels',
        })
      );

      // Tags like "P1 1200 kW", "FM-03 42.1 L/s"
      const tagsData = [
        ...pumpUnitsData.map((u) => ({ coord: u.coord, tag: u.tag })),
        { coord: fmCoord, tag: siteConfig.instrumentation.flow_meter.tag },
        { coord: ptCoord, tag: siteConfig.instrumentation.pressure_transmitter.tag },
      ];

      layers.push(
        new TextLayer({
          id: 'site-plan-tags',
          data: tagsData,
          getPosition: (d: any) => d.coord,
          getText: (d: any) => d.tag,
          getSize: 12,
          getColor: () => [241, 245, 249, 255],
          getPixelOffset: [0, 26],
          getTextAnchor: 'middle',
          fontFamily: 'monospace',
          outlineWidth: 3,
          outlineColor: [2, 6, 23, 255],
          fontSettings: { sdf: true },
        })
      );
    }
  }

  const extraLayers = layerRegistry.getAllLayers(props);
  if (extraLayers.length > 0) {
    layers.push(...extraLayers);
  }

  // ---------------------------------------------------------------------------
  // Leak Demo Callout & Pulsing Marker (shows approx leaking amount & location)
  // ---------------------------------------------------------------------------
  if (props.demoStatus && props.demoStatus.state !== 'IDLE' && props.demoStatus.state !== 'RESTORED') {
    const leakCoords = props.demoStatus.config?.leak_coordinates || [77.5380, 12.9050];
    const leakLps = props.demoStatus.config?.leak_rate_lps || 45.0;
    const leakKld = Math.round(leakLps * 86.4);
    const landmark = props.demoStatus.config?.landmark || 'Pipeline Road Ch 6+400';
    const ward = props.demoStatus.selected_ward || 'Basavanagudi';

    const handleLeakClick = () => {
      if (props.onNavigateToMonitor) {
        props.onNavigateToMonitor();
      }
    };

    layers.push(
      new ScatterplotLayer({
        id: 'leak-pulsing-beacon',
        data: [{ position: leakCoords }],
        getPosition: (d: any) => d.position,
        getRadius: 28 + Math.sin(currentTime * 4) * 8,
        radiusUnits: 'pixels',
        getFillColor: [239, 68, 68, 160],
        getLineColor: [255, 255, 255, 240],
        getLineWidth: 2.5,
        lineWidthUnits: 'pixels',
        pickable: true,
        onClick: handleLeakClick,
      })
    );

    layers.push(
      new TextLayer({
        id: 'leak-approx-amount-badge',
        data: [{
          position: leakCoords,
          text: `[LEAK] ~${leakLps.toFixed(1)} L/s (${leakKld.toLocaleString()} kL/day)\n[LOCATION] ${ward} - ${landmark}\n(Click to open Monitor)`
        }],
        getPosition: (d: any) => d.position,
        getText: (d: any) => d.text,
        getSize: 12,
        getColor: [255, 255, 255, 255],
        getPixelOffset: [0, -32],
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'bottom',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 700,
        background: true,
        getBackgroundColor: () => [190, 24, 24, 240],
        backgroundPadding: [8, 6],
        fontSettings: { sdf: true },
        outlineWidth: 2,
        outlineColor: [0, 0, 0, 220],
        pickable: true,
        onClick: handleLeakClick,
      })
    );
  }

  return layers;
}
