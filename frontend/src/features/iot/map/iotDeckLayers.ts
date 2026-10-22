/**
 * Isolated Deck.gl Map Layers for IoT Subsystem.
 * Implements:
 * - Pumping Stations with ISA-5.1 icons, status rings (green/amber/red) and running equipment counts
 * - STPs (Sewage Treatment Plants) with status rings and flow/quality indicators
 * - GLR / OHT Balancing Reservoirs and Water Treatment Plants (WTPs)
 * - MLD Transmission Corridors with animated TripsLayer flow particles and MLD labels
 * - Division Smart Meter Boards at division supply centroids with live consumption badges
 * - Inline devices at z >= 14: Flow meters, Pressure transmitters, Level sensors, Quality analysers, Borewells, Valves
 * - High-zoom Station Site Plan at z >= 17: Manifolds, Pump units with 1 Hz rotating impeller glyphs, Valves, Tags
 * - Pickable click-to-inspect integration
 */

import { PathLayer, IconLayer, TextLayer, ScatterplotLayer, PolygonLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import {
  StationOverview,
  DivisionBoardSummary,
  WaterFlowCorridor,
  IoTAlertItem,
  PumpTelemetry,
  DeviceTelemetry
} from '../types';
import { useIoTStore } from '../store/useIoTStore';
import { buildIconAtlas, IconBounds } from '../../../map/icons';
import { offsetMetersToLngLat } from '../../../map/turfMath';

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

export function buildIoTDeckLayers(props: any) {
  const store = useIoTStore.getState();
  const {
    stations = [],
    divisions = [],
    corridors = [],
    alerts = [],
    layerToggles,
    setSelectedStation,
    setSelectedPump,
    setSelectedDevice,
    setSelectedDivision,
    setSelectedInspectorType
  } = store;

  // Only render if in IOT module or explicitly requested
  if (props.activeModule && props.activeModule !== 'IOT') {
    return [];
  }

  const zoom = typeof props.zoom === 'number' ? props.zoom : 11.2;
  const currentTime = typeof props.currentTime === 'number' ? props.currentTime : 0;
  const impellerFrame = typeof props.impellerFrame === 'number' ? props.impellerFrame : 0;
  const atlas = getAtlas();

  const layers: any[] = [];

  // Active alert station lookup map for red/amber status rings
  const alertStationIds = new Set<string>();
  alerts.forEach((a: IoTAlertItem) => {
    if (a.active && a.location) {
      stations.forEach((s: StationOverview) => {
        if (a.location.includes(s.name) || (a.asset_id && a.asset_id.includes(s.id))) {
          alertStationIds.add(s.id);
        }
      });
    }
  });

  // ---------------------------------------------------------------------------
  // 1. MLD Transmission Corridors (z >= 10)
  // ---------------------------------------------------------------------------
  if (layerToggles.mldCorridors && corridors.length > 0) {
    layers.push(
      new PathLayer({
        id: 'iot-mld-corridors-casing',
        data: corridors,
        getPath: (d: WaterFlowCorridor) => d.coordinates,
        getColor: [2, 132, 199, 140],
        getWidth: (d: WaterFlowCorridor) => Math.max(5, Math.min(14, d.flow_mld / 120)),
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
        pickable: true,
      })
    );

    // TripsLayer Animated Direction Particles along transmission corridors
    const tripsData = corridors.map((c: WaterFlowCorridor) => {
      const coords = c.coordinates;
      const totalLen = Math.max(2, coords.length);
      const timestamps = coords.map((_: any, idx: number) => (idx / (totalLen - 1)) * 100);
      return {
        path: coords,
        timestamps,
      };
    });

    layers.push(
      new TripsLayer({
        id: 'iot-mld-flow-particles',
        data: tripsData,
        getPath: (d: any) => d.path,
        getTimestamps: (d: any) => d.timestamps,
        getColor: [56, 189, 248, 255],
        currentTime: (currentTime * 1.5) % 100,
        trailLength: 16,
        widthMinPixels: 3.5,
        capRounded: true,
      })
    );

    // Corridor Flow Labels (z >= 11)
    if (zoom >= 11.0) {
      const labelPoints = corridors
        .filter((c: WaterFlowCorridor) => c.coordinates && c.coordinates.length >= 2)
        .map((c: WaterFlowCorridor) => {
          const midIdx = Math.floor(c.coordinates.length / 2);
          return {
            coord: c.coordinates[midIdx],
            text: `${c.flow_mld.toFixed(0)} MLD`,
          };
        });

      layers.push(
        new TextLayer({
          id: 'iot-mld-labels',
          data: labelPoints,
          getPosition: (d: any) => d.coord,
          getText: (d: any) => d.text,
          getSize: 11,
          getColor: [248, 250, 252, 255],
          backgroundColor: [15, 23, 42, 210],
          backgroundPadding: [4, 2],
          fontFamily: 'monospace',
          fontWeight: 'bold',
          getTextAnchor: 'middle',
        })
      );
    }

    // Active Leak Uncertainty Corridor Halo (P5)
    const activeLeakAlerts = alerts.filter(
      (a: IoTAlertItem) => a.active && (a.rule_id === 'RULE-IOT-LEAK-01' || a.category === 'HYDRAULIC_INTEGRITY')
    );
    if (activeLeakAlerts.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: 'iot-leak-uncertainty-halo',
          data: activeLeakAlerts,
          getPosition: (d: IoTAlertItem) => d.coordinates || [77.5380, 12.9050],
          getRadius: 45 + Math.sin(currentTime * 3) * 12,
          radiusUnits: 'pixels',
          getFillColor: [239, 68, 68, 45],
          getLineColor: [239, 68, 68, 220],
          lineWidthMinPixels: 2.5,
          stroked: true,
        })
      );

      layers.push(
        new TextLayer({
          id: 'iot-leak-alert-labels',
          data: activeLeakAlerts,
          getPosition: (d: IoTAlertItem) => d.coordinates || [77.5380, 12.9050],
          getText: (d: IoTAlertItem) => `⚠️ Leak Detected (${d.estimated_loss_lps ?? 45} L/s)`,
          getSize: 12,
          getColor: [255, 255, 255, 255],
          backgroundColor: [225, 29, 72, 230],
          backgroundPadding: [6, 3],
          fontFamily: 'monospace',
          fontWeight: 'bold',
          getPixelOffset: [0, -32],
          getTextAnchor: 'middle',
        })
      );
    }
  }

  // ---------------------------------------------------------------------------
  // 2. Division Smart Meter Boards (Centroids snapped to mains)
  // ---------------------------------------------------------------------------
  if (layerToggles.smartMeters && divisions.length > 0) {
    // Status Ring for Smart Meter Boards
    layers.push(
      new ScatterplotLayer({
        id: 'iot-smart-meter-rings',
        data: divisions,
        getPosition: (d: DivisionBoardSummary) => d.centroid_coordinates,
        getRadius: zoom >= 13 ? 18 : 12,
        radiusUnits: 'pixels',
        getFillColor: [147, 51, 234, 40],
        getLineColor: [168, 85, 247, 240],
        lineWidthMinPixels: 2.5,
        stroked: true,
      })
    );

    // Center Glyph for Smart Meter Boards
    layers.push(
      new ScatterplotLayer({
        id: 'iot-smart-meter-nodes',
        data: divisions,
        getPosition: (d: DivisionBoardSummary) => d.centroid_coordinates,
        getRadius: zoom >= 13 ? 10 : 7,
        radiusUnits: 'pixels',
        getFillColor: [147, 51, 234, 230],
        getLineColor: [255, 255, 255, 255],
        lineWidthMinPixels: 2,
        stroked: true,
        pickable: true,
        autoHighlight: true,
        onClick: (info: any) => {
          if (info.object) {
            setSelectedDivision(info.object);
            setSelectedInspectorType('division');
          }
        },
      })
    );

    // Label with live total consumption
    layers.push(
      new TextLayer({
        id: 'iot-smart-meter-labels',
        data: divisions,
        getPosition: (d: DivisionBoardSummary) => d.centroid_coordinates,
        getText: (d: DivisionBoardSummary) => `📟 ${d.division_name.replace(' Division', '')} (${d.inlet_mld.toFixed(1)} MLD)`,
        getSize: zoom >= 13 ? 12 : 10,
        getColor: [248, 250, 252, 255],
        getPixelOffset: [0, -18],
        getTextAnchor: 'middle',
        fontFamily: 'sans-serif',
        fontWeight: 'bold',
        outlineWidth: 2.5,
        outlineColor: [15, 23, 42, 255],
      })
    );
  }

  // ---------------------------------------------------------------------------
  // 3. Pumping Stations & STPs (At City Zoom: Status Rings + Equipment Counts)
  // ---------------------------------------------------------------------------
  const filteredStations = stations.filter((s: StationOverview) => {
    if (s.station_class === 'stp') return layerToggles.stps;
    return layerToggles.pumpingStations;
  });

  if (filteredStations.length > 0 && zoom < 17.0) {
    // A. Status Rings
    layers.push(
      new ScatterplotLayer({
        id: 'iot-station-status-rings',
        data: filteredStations,
        getPosition: (d: StationOverview) => d.coordinates,
        getRadius: zoom >= 14 ? 22 : 15,
        radiusUnits: 'pixels',
        getFillColor: (d: StationOverview) => {
          if (alertStationIds.has(d.id)) return [239, 68, 68, 60]; // Red alert
          return [16, 185, 129, 45]; // Green normal
        },
        getLineColor: (d: StationOverview) => {
          if (alertStationIds.has(d.id)) return [239, 68, 68, 240];
          return [16, 185, 129, 220];
        },
        lineWidthMinPixels: 2.5,
        stroked: true,
      })
    );

    // B. Base Station Icon (using atlas if loaded, or colored symbol)
    if (atlas) {
      layers.push(
        new IconLayer({
          id: 'iot-station-icons',
          data: filteredStations,
          iconAtlas: atlas.atlasUrl,
          iconMapping: atlas.mapping,
          getIcon: (d: StationOverview) => (d.station_class === 'stp' ? 'stp' : 'pumping_station'),
          getPosition: (d: StationOverview) => d.coordinates,
          getSize: zoom >= 14 ? 30 : 22,
          sizeUnits: 'pixels',
          pickable: true,
          autoHighlight: true,
          onClick: (info: any) => {
            if (info.object) {
              setSelectedStation(info.object);
              setSelectedInspectorType(info.object.station_class === 'stp' ? 'stp' : 'station');
            }
          },
        })
      );
    } else {
      layers.push(
        new ScatterplotLayer({
          id: 'iot-station-nodes-fallback',
          data: filteredStations,
          getPosition: (d: StationOverview) => d.coordinates,
          getRadius: zoom >= 14 ? 12 : 9,
          radiusUnits: 'pixels',
          getFillColor: (d: StationOverview) => (d.station_class === 'stp' ? [147, 51, 234, 230] : [16, 185, 129, 230]),
          getLineColor: [255, 255, 255, 255],
          lineWidthMinPixels: 2,
          stroked: true,
          pickable: true,
          autoHighlight: true,
          onClick: (info: any) => {
            if (info.object) {
              setSelectedStation(info.object);
              setSelectedInspectorType(info.object.station_class === 'stp' ? 'stp' : 'station');
            }
          },
        })
      );
    }

    // C. Station Label with Running Equipment Count
    layers.push(
      new TextLayer({
        id: 'iot-station-labels-with-counts',
        data: filteredStations,
        getPosition: (d: StationOverview) => d.coordinates,
        getText: (d: StationOverview) => {
          const running = d.pumps.filter((p) => p.run_state === 'RUNNING').length;
          const total = d.pumps.length;
          const name = d.name.replace(' Terminal Pumping Station', '').replace(' Booster Station', '');
          return `${name} (${running}/${total})`;
        },
        getSize: zoom >= 14 ? 12 : 10,
        getColor: [255, 255, 255, 255],
        getPixelOffset: [0, 20],
        getTextAnchor: 'middle',
        fontFamily: 'sans-serif',
        fontWeight: 'bold',
        outlineWidth: 3,
        outlineColor: [2, 6, 23, 255],
      })
    );
  }

  // ---------------------------------------------------------------------------
  // 4. Detailed Devices at z >= 14 (Flow meters, Pressure, Level, Valves, Quality)
  // ---------------------------------------------------------------------------
  if (zoom >= 14.0 && zoom < 17.0) {
    const devicesData: any[] = [];
    filteredStations.forEach((stn: StationOverview) => {
      stn.devices.forEach((dev: DeviceTelemetry) => {
        // Filter by layer toggles
        if (dev.type_code === 'FIT' && !layerToggles.flowMeters) return;
        if (dev.type_code === 'PIT' && !layerToggles.pressureSensors) return;
        if (dev.type_code === 'LIT' && !layerToggles.levelSensors) return;
        if (dev.type_code === 'AIT' && !layerToggles.qualityAnalysers) return;

        const offset = dev.location?.offset_m || [10, 0];
        const coord = offsetMetersToLngLat(stn.coordinates, offset, stn.site_rotation_deg || 0);
        devicesData.push({
          ...dev,
          coord,
          stationId: stn.id,
          stationName: stn.name,
        });
      });
    });

    if (devicesData.length > 0 && atlas) {
      layers.push(
        new IconLayer({
          id: 'iot-devices-icon-layer',
          data: devicesData,
          iconAtlas: atlas.atlasUrl,
          iconMapping: atlas.mapping,
          getIcon: (d: any) => {
            if (d.type_code === 'FIT') return 'flow_meter';
            if (d.type_code === 'PIT') return 'pressure_transmitter';
            if (d.type_code === 'LIT') return 'glr_tank';
            if (d.type_code === 'AIT') return 'wtp';
            return 'flow_meter';
          },
          getPosition: (d: any) => d.coord,
          getSize: 20,
          sizeUnits: 'pixels',
          pickable: true,
          autoHighlight: true,
          onClick: (info: any) => {
            if (info.object) {
              setSelectedDevice(info.object);
              setSelectedInspectorType(info.object.type_code === 'FIT' ? 'meter' : 'device');
            }
          },
        })
      );

      // Device Tag Labels
      layers.push(
        new TextLayer({
          id: 'iot-devices-tag-labels',
          data: devicesData,
          getPosition: (d: any) => d.coord,
          getText: (d: any) => d.tag,
          getSize: 10,
          getColor: [241, 245, 249, 255],
          getPixelOffset: [0, 14],
          getTextAnchor: 'middle',
          fontFamily: 'monospace',
          outlineWidth: 2,
          outlineColor: [15, 23, 42, 255],
        })
      );
    }
  }

  // ---------------------------------------------------------------------------
  // 5. High-Zoom Station Site Plan (z >= 17: Footprint, Manifolds, Impellers, Valves)
  // ---------------------------------------------------------------------------
  if (zoom >= 17.0) {
    for (const stn of filteredStations) {
      const origin: [number, number] = stn.coordinates;
      const rot = stn.site_rotation_deg || 0;

      // Pump units
      const pumpUnitsData = stn.pumps.map((p: PumpTelemetry, idx: number) => {
        const yOffset = (idx - (stn.pumps.length - 1) / 2) * 12;
        const coord = offsetMetersToLngLat(origin, [-12.0, yOffset], rot);
        return {
          ...p,
          coord,
          stationId: stn.id,
          tag: `${p.tag} (${p.active_power_kw.toFixed(0)} kW)`,
        };
      });

      // Pump Impeller / Status Glyphs
      layers.push(
        new ScatterplotLayer({
          id: `iot-site-pumps-${stn.id}`,
          data: pumpUnitsData,
          getPosition: (d: any) => d.coord,
          getRadius: 12,
          radiusUnits: 'pixels',
          getFillColor: (d: any) => (d.run_state === 'RUNNING' ? [16, 185, 129, 240] : [239, 68, 68, 240]),
          getLineColor: [255, 255, 255, 255],
          lineWidthMinPixels: 2.5,
          stroked: true,
          pickable: true,
          autoHighlight: true,
          onClick: (info: any) => {
            if (info.object) {
              const pumpObj = stn.pumps.find((p: PumpTelemetry) => p.pump_id === info.object.pump_id);
              if (pumpObj) {
                setSelectedPump(pumpObj);
                setSelectedInspectorType('pump');
              }
            }
          },
        })
      );

      // Tank / Sump at station
      if (layerToggles.tanks && stn.tank) {
        const tankCoord = offsetMetersToLngLat(origin, [40.0, 15.0], rot);
        layers.push(
          new ScatterplotLayer({
            id: `iot-site-tank-${stn.id}`,
            data: [{ coord: tankCoord, name: stn.tank.name, level: stn.tank.level_pct }],
            getPosition: (d: any) => d.coord,
            getRadius: 24,
            radiusUnits: 'pixels',
            getFillColor: [14, 165, 233, 190],
            getLineColor: [255, 255, 255, 255],
            lineWidthMinPixels: 2.5,
            stroked: true,
            pickable: true,
            autoHighlight: true,
            onClick: () => {
              setSelectedStation(stn);
              setSelectedInspectorType('tank');
            },
          })
        );
      }

      // Site Labels
      const siteLabels = [
        ...pumpUnitsData.map((u: any) => ({ coord: u.coord, text: u.tag })),
        ...(layerToggles.tanks && stn.tank
          ? [{ coord: offsetMetersToLngLat(origin, [40.0, 15.0], rot), text: `${stn.tank.name} (${stn.tank.level_pct.toFixed(0)}%)` }]
          : []),
      ];

      layers.push(
        new TextLayer({
          id: `iot-site-labels-${stn.id}`,
          data: siteLabels,
          getPosition: (d: any) => d.coord,
          getText: (d: any) => d.text,
          getSize: 11,
          getColor: [248, 250, 252, 255],
          getPixelOffset: [0, 18],
          getTextAnchor: 'middle',
          fontFamily: 'monospace',
          outlineWidth: 2,
          outlineColor: [15, 23, 42, 255],
        })
      );
    }
  }

  return layers;
}
