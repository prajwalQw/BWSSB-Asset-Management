/**
 * Isolated Deck.gl Map Layers for IoT Subsystem.
 * Includes:
 * - IoT Pumping Stations & Pump Set Glyphs
 * - High-zoom site plan (z >= 17) with H1-H3 / F1-F2 pump units, flow sensors, meters, IoT boards, and tank
 * - Smart Meter Boards at division centroids
 * - MLD Transmission Corridors with animated particles (width scaled to flow)
 * - Instrument tags and status rings
 */

import { PathLayer, IconLayer, TextLayer, ScatterplotLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import { StationOverview, DivisionBoardSummary, WaterFlowCorridor } from '../types';
import { offsetMetersToLngLat } from '../../../map/turfMath';

export interface IoTDeckLayerProps {
  zoom: number;
  currentTime: number;
  stations: StationOverview[];
  divisions: DivisionBoardSummary[];
  corridors: WaterFlowCorridor[];
  selectedId?: string | null;
  onSelectStation?: (stn: StationOverview) => void;
  onSelectPump?: (pumpId: string) => void;
  onSelectDivision?: (divName: string) => void;
}

export function buildIoTDeckLayers({
  zoom,
  currentTime,
  stations,
  divisions,
  corridors,
  selectedId,
  onSelectStation,
  onSelectPump,
  onSelectDivision,
}: IoTDeckLayerProps) {
  const layers: any[] = [];

  // 1. MLD Transmission Corridors (PathLayer with width scaled to MLD)
  if (corridors.length > 0) {
    layers.push(
      new PathLayer({
        id: 'iot-mld-corridors-casing',
        data: corridors,
        getPath: (d: WaterFlowCorridor) => d.coordinates,
        getColor: [2, 132, 199, 140],
        getWidth: (d: WaterFlowCorridor) => Math.max(4, Math.min(14, (d.flow_mld / 150))),
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
        pickable: true,
      })
    );

    // Dynamic TripsLayer Animated Direction Particles along transmission corridors
    const tripsData = corridors.map((c) => {
      const coords = c.coordinates;
      const totalLen = coords.length;
      const timestamps = coords.map((_, idx) => (idx / (totalLen - 1)) * 100);
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
        trailLength: 15,
        widthMinPixels: 3,
        capRounded: true,
      })
    );

    // MLD Labels along corridors (at zoom >= 11)
    if (zoom >= 11.0) {
      const labelPoints = corridors.map((c) => {
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
          backgroundColor: [15, 23, 42, 200],
          backgroundPadding: [4, 2],
          fontFamily: 'monospace',
          fontWeight: 'bold',
          getTextAnchor: 'middle',
        })
      );
    }
  }

  // 2. Smart Meter Boards at Division Centroids
  if (divisions.length > 0) {
    layers.push(
      new ScatterplotLayer({
        id: 'iot-division-smart-meters',
        data: divisions,
        getPosition: (d: DivisionBoardSummary) => d.centroid_coordinates,
        getRadius: zoom >= 13 ? 12 : 8,
        radiusUnits: 'pixels',
        getFillColor: [147, 51, 234, 220],
        getLineColor: [255, 255, 255, 255],
        lineWidthMinPixels: 2,
        stroked: true,
        pickable: true,
        onClick: (info: any) => {
          if (info.object && onSelectDivision) {
            onSelectDivision(info.object.division_name);
          }
        },
      })
    );

    layers.push(
      new TextLayer({
        id: 'iot-division-labels',
        data: divisions,
        getPosition: (d: DivisionBoardSummary) => d.centroid_coordinates,
        getText: (d: DivisionBoardSummary) => `📟 ${d.division_name.replace(' Division', '')}`,
        getSize: 11,
        getColor: [241, 245, 249, 255],
        getPixelOffset: [0, -18],
        getTextAnchor: 'middle',
        fontFamily: 'sans-serif',
        fontWeight: 'bold',
        outlineWidth: 2,
        outlineColor: [15, 23, 42, 255],
      })
    );
  }

  // 3. IoT Pumping Stations Symbols (Zoom < 17)
  if (zoom < 17.0) {
    layers.push(
      new ScatterplotLayer({
        id: 'iot-stations-points',
        data: stations,
        getPosition: (d: StationOverview) => d.coordinates,
        getRadius: zoom >= 14 ? 14 : 9,
        radiusUnits: 'pixels',
        getFillColor: [16, 185, 129, 220],
        getLineColor: [255, 255, 255, 255],
        lineWidthMinPixels: 2,
        stroked: true,
        pickable: true,
        onClick: (info: any) => {
          if (info.object && onSelectStation) {
            onSelectStation(info.object);
          }
        },
      })
    );

    layers.push(
      new TextLayer({
        id: 'iot-station-labels',
        data: stations,
        getPosition: (d: StationOverview) => d.coordinates,
        getText: (d: StationOverview) => d.name,
        getSize: 12,
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

  // 4. High-Zoom Site Plan at z >= 17: H1-H3 / F1-F2 Pump Sets, Flow Meters, Tank
  if (zoom >= 17.0) {
    for (const stn of stations) {
      const origin: [number, number] = stn.coordinates;
      const rot = stn.site_rotation_deg;

      // Pump units
      const pumpUnitsData = stn.pumps.map((p, idx) => {
        const yOffset = (idx - (stn.pumps.length - 1) / 2) * 10;
        const coord = offsetMetersToLngLat(origin, [-12.0, yOffset], rot);
        return {
          ...p,
          coord,
          tag: `${p.tag} (${p.active_power_kw.toFixed(0)} kW)`,
        };
      });

      layers.push(
        new ScatterplotLayer({
          id: `iot-site-pumps-${stn.id}`,
          data: pumpUnitsData,
          getPosition: (d: any) => d.coord,
          getRadius: 10,
          radiusUnits: 'pixels',
          getFillColor: (d: any) => (d.run_state === 'RUNNING' ? [16, 185, 129, 255] : [239, 68, 68, 255]),
          getLineColor: [255, 255, 255, 255],
          lineWidthMinPixels: 2,
          stroked: true,
          pickable: true,
          onClick: (info: any) => {
            if (info.object && onSelectPump) {
              onSelectPump(info.object.pump_id);
            }
          },
        })
      );

      // Tank glyph at offset
      const tankCoord = offsetMetersToLngLat(origin, [40.0, 15.0], rot);
      layers.push(
        new ScatterplotLayer({
          id: `iot-site-tank-${stn.id}`,
          data: [{ coord: tankCoord, name: stn.tank.name, level: stn.tank.level_pct }],
          getPosition: (d: any) => d.coord,
          getRadius: 22,
          radiusUnits: 'pixels',
          getFillColor: [14, 165, 233, 180],
          getLineColor: [255, 255, 255, 255],
          lineWidthMinPixels: 2,
          stroked: true,
          pickable: true,
        })
      );

      // Labels on site elements
      const siteLabels = [
        ...pumpUnitsData.map((u) => ({ coord: u.coord, text: u.tag })),
        { coord: tankCoord, text: `${stn.tank.name} (${stn.tank.level_pct.toFixed(0)}%)` },
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
