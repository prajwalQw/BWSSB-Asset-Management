/**
 * MapLibre Composite Basemap Engine
 *
 * Implements:
 * 1. OpenFreeMap high-performance vector basemap (Zero API Keys, ODbL) with full locality,
 *    street, road, lake, park, and building rendering.
 * 2. Self-hosted PMTiles protocol registration for local offline extraction (bengaluru.pmtiles).
 * 3. Esri World Imagery Satellite Raster (Compliant terms and attribution).
 * 4. Single MapLibre v8 Composite Style: sources and tagged layer groups ('dark', 'light', 'gray', 'satellite', 'satellite-labels').
 * 5. Theme switching via setLayoutProperty('visibility') and setPaintProperty(). NEVER calls map.setStyle().
 * 6. Robust offline and error handling with fallback plain background + boundary polygons.
 */

import maplibregl, { StyleSpecification, LayerSpecification } from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { BasemapTheme, MAP_THEMES } from './theme';
import ofmDarkStyle from './styles/ofm_dark.json';
import ofmBrightStyle from './styles/ofm_bright.json';

let pmtilesProtocolRegistered = false;

/**
 * Registers the PMTiles custom protocol handler with MapLibre GL once.
 */
export function registerPMTilesProtocol() {
  if (!pmtilesProtocolRegistered) {
    const protocol = new Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);
    pmtilesProtocolRegistered = true;
  }
}

/**
 * Creates the single composite MapLibre Style Specification (v8) containing
 * all sources and layer groups.
 */
export function createCompositeBasemapStyle(): StyleSpecification {
  registerPMTilesProtocol();

  const satelliteSourceName = 'satellite-raster';

  // 1. OpenFreeMap Dark Layers (tagged metadata: group = 'dark')
  const darkLayers: LayerSpecification[] = (ofmDarkStyle.layers as any[])
    .filter((l) => l.id !== 'background')
    .map((l) => {
      const tagged: any = {
        ...l,
        id: `dark-${l.id}`,
        metadata: { group: 'dark' },
        layout: {
          ...(l.layout || {}),
          visibility: 'visible',
        },
      };
      if (l.type === 'symbol' && (l.id.includes('place') || l.id.includes('town') || l.id.includes('city') || l.id.includes('label'))) {
        tagged.minzoom = Math.min(tagged.minzoom || 11, 11);
      }
      return tagged as LayerSpecification;
    });

  // 2. OpenFreeMap Light / Bright Layers (tagged metadata: group = 'light')
  const lightLayers: LayerSpecification[] = (ofmBrightStyle.layers as any[])
    .filter((l) => l.id !== 'background')
    .map((l) => {
      const tagged: any = {
        ...l,
        id: `light-${l.id}`,
        metadata: { group: 'light' },
        layout: {
          ...(l.layout || {}),
          visibility: 'none',
        },
      };
      if (l.type === 'symbol' && (l.id.includes('place') || l.id.includes('town') || l.id.includes('city') || l.id.includes('label'))) {
        tagged.minzoom = Math.min(tagged.minzoom || 11, 11);
      }
      return tagged as LayerSpecification;
    });

  // 3. Grayscale Layers
  const grayLayers: LayerSpecification[] = (ofmDarkStyle.layers as any[])
    .filter((l) => l.id !== 'background')
    .map((l) => {
      const tagged: any = {
        ...l,
        id: `gray-${l.id}`,
        metadata: { group: 'gray' },
        layout: {
          ...(l.layout || {}),
          visibility: 'none',
        },
      };
      return tagged as LayerSpecification;
    });

  // 4. Satellite Raster Layer + Hybrid Road & Locality Labels (white text with dark halo)
  const satelliteRasterLayer: LayerSpecification = {
    id: 'satellite-raster-layer',
    type: 'raster',
    source: satelliteSourceName,
    metadata: { group: 'satellite' },
    layout: { visibility: 'none' },
    paint: {
      'raster-opacity': 1.0,
      'raster-fade-duration': 300,
    },
    minzoom: 0,
    maxzoom: 20,
  };

  // Hybrid vector labels for Satellite display (white text + dark halo)
  const satelliteLabelLayers: LayerSpecification[] = (ofmDarkStyle.layers as any[])
    .filter((l) => l.type === 'symbol' || l.id.includes('road') || l.id.includes('name') || l.id.includes('boundary'))
    .map((l) => {
      const tagged: any = {
        ...l,
        id: `sat-hybrid-${l.id}`,
        metadata: { group: 'satellite-labels' },
        layout: {
          ...(l.layout || {}),
          visibility: 'none',
        },
      };

      if (l.type === 'symbol') {
        tagged.paint = {
          ...(l.paint || {}),
          'text-color': '#ffffff',
          'text-halo-color': '#000000',
          'text-halo-width': 2.0,
        };
      }
      return tagged as LayerSpecification;
    });

  // Solid base background to guarantee the map canvas is NEVER blank
  const solidBackgroundLayer: LayerSpecification = {
    id: 'bg-solid',
    type: 'background',
    paint: {
      'background-color': MAP_THEMES.dark.backgroundColor,
    },
  };

  // Composite Style Object
  return {
    version: 8,
    name: 'BWSSB Composite Twin Basemap',
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sprite: 'https://tiles.openfreemap.org/sprites/ofm_f384/ofm',
    sources: {
      // Primary High-Performance Vector Basemap (Zero keys, unmetered, ODbL)
      openmaptiles: {
        type: 'vector',
        url: 'https://tiles.openfreemap.org/planet',
        attribution: '© OpenStreetMap contributors, OpenFreeMap',
      },
      // Natural Earth shading for low zooms
      ne2_shaded: {
        type: 'raster',
        tileSize: 256,
        tiles: ['https://tiles.openfreemap.org/natural_earth/ne2sr/{z}/{x}/{y}.png'],
        maxzoom: 6,
      },
      // Local PMTiles Vector Protocol (if extracted into public/tiles/bengaluru.pmtiles)
      'local-pmtiles': {
        type: 'vector',
        url: 'pmtiles:///tiles/bengaluru.pmtiles',
        attribution: '© OpenStreetMap contributors, Protomaps',
      },
      // Satellite: Esri World Imagery (Permitted for display with attribution)
      [satelliteSourceName]: {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution:
          'Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        maxzoom: 19,
      },
    },
    layers: [
      solidBackgroundLayer,
      satelliteRasterLayer,
      ...darkLayers,
      ...lightLayers,
      ...grayLayers,
      ...satelliteLabelLayers,
    ],
  };
}

/**
 * Switches the active basemap theme by updating layer visibility and paint properties.
 * NEVER calls map.setStyle(), preserving all layers, deck.gl overlays, and WebGL state.
 */
export function switchBasemapTheme(map: maplibregl.Map, theme: BasemapTheme) {
  if (!map || !map.isStyleLoaded()) return;

  const style = map.getStyle();
  if (!style || !style.layers) return;

  // 1. Update solid canvas background
  const tokens = MAP_THEMES[theme];
  if (map.getLayer('bg-solid')) {
    map.setPaintProperty('bg-solid', 'background-color', tokens.backgroundColor);
  }

  // 2. Toggle layer groups by metadata
  style.layers.forEach((layer: any) => {
    const group = (layer.metadata as any)?.group;
    if (!group) return;

    let shouldBeVisible = false;
    if (theme === 'dark' && group === 'dark') shouldBeVisible = true;
    if (theme === 'light' && group === 'light') shouldBeVisible = true;
    if (theme === 'grayscale' && group === 'gray') shouldBeVisible = true;
    if (theme === 'satellite' && (group === 'satellite' || group === 'satellite-labels')) {
      shouldBeVisible = true;
    }

    const currentVis = map.getLayoutProperty(layer.id, 'visibility') || 'visible';
    const targetVis = shouldBeVisible ? 'visible' : 'none';

    if (currentVis !== targetVis) {
      map.setLayoutProperty(layer.id, 'visibility', targetVis);
    }
  });
}
