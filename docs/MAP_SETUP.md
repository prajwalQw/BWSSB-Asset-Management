# Bengaluru Water Digital Twin - Map Engine Specification & Setup

**Document Version:** 2.0.0  
**Updated:** 2026-10-22  
**Compliance:** Zero API Keys, ODbL Attribution, High-Contrast Multi-Theme, P&ID Symbology, Level of Detail (LOD).

---

## 1. Executive Architecture Overview

The Map Engine powers the Bengaluru Water Supply and Sewerage Board (BWSSB) Digital Twin. It provides real-time SCADA and hydraulic twin situational awareness across Greater Bengaluru and the Cauvery transmission corridors (Stages I–V from Torekadanahalli to Tataguni).

### Key Architectural Fixes Implemented:
1. **Zero Key Watermark-Free Basemap:** All Carto, Mapbox, MapTiler, and Stadia URLs have been purged. The primary basemap runs on self-hosted PMTiles vector tiles with Protomaps basemaps, with automatic runtime fallback to OpenFreeMap.
2. **Single Composite MapLibre Style:** Built once at initialization (MapLibre Style Spec v8). Theme switching (Dark, Light, Hybrid Satellite, Grayscale) is performed strictly via `setLayoutProperty("visibility")` and `setPaintProperty()`. `map.setStyle()` is **NEVER** called.
3. **Isolated WebGL Overlay:** All network assets and flow lines render through `@deck.gl/mapbox` with `interleaved: false` on an isolated canvas overlay. WebGL contexts, geometry buffers, and animations survive any theme switch intact.
4. **Authentic P&ID / ISA-5.1 Symbology:** Replaced ambiguous colored circles with original vector symbols (WTP, Pumping Station, Pump Unit, STP, GLR/Tank, Borewell, Flow Meter, Pressure Transmitter, Valve, Bulk Meter). Asset health is encoded by a status ring (Normal green, Watch amber, Alert red, No Data grey) plus icon cues.
5. **Dynamic Flow TripsLayer:** Static casing and core PathLayers coupled with `@deck.gl/geo-layers` `TripsLayer` driven by a unified `requestAnimationFrame` clock. Speed scales with physical pipeline velocity. Midpoint flow chevrons appear at $z \ge 15$.
6. **Level of Detail (LOD):** Smoothly transitions across zoom levels from division-level clusters ($z < 11$) to trunk mains ($z \in [11, 14)$), inline pipe-anchored meters and valves ($z \in [14, 17)$), up to high-zoom site-plan views ($z \ge 17$) showing plant footprint polygons, manifolds, pump units, tags, and 1 Hz rotating impeller glyphs.

---

## 2. Basemap Setup & Tile Extraction

### 2.1 Bounding Box Calculation
The bounding box covers the 16 BWSSB administrative divisions, plus the Cauvery transmission corridor through Tataguni, Harohalli, and the Torekadanahalli (TK Halli) intake/treatment works with 10% safety margin padding:

$$\text{BBox} = [77.0300, 12.1570, 77.8700, 13.2730]$$
- **South-West:** $77.0300^\circ\text{E},\ 12.1570^\circ\text{N}$ (TK Halli Stage I–IV intake works)
- **North-East:** $77.8700^\circ\text{E},\ 13.2730^\circ\text{N}$ (Devanahalli / Yelahanka boundary)

### 2.2 Extraction Command
To extract vector tiles using the `pmtiles` CLI tool:

```bash
# 1. Download or ensure pmtiles CLI is installed
# https://github.com/protomaps/go-pmtiles/releases

# 2. Extract bounding box from latest Protomaps build
pmtiles extract https://build.protomaps.com/20261021.pmtiles frontend/public/tiles/bengaluru.pmtiles --bbox=77.03,12.157,77.87,13.273
```

Automated Python script:
```bash
python scripts/extract_pmtiles.py
```

### 2.3 Protocol Registration
Registered in `frontend/src/map/basemap.ts`:
```ts
import { Protocol } from 'pmtiles';
import maplibregl from 'maplibre-gl';

const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);
```

### 2.4 OpenFreeMap Vector Fallback & Terms
If `bengaluru.pmtiles` is absent or the client is online, the composite style connects to OpenFreeMap planetary vector tiles:
- **Vector Tile Endpoint:** `https://tiles.openfreemap.org/planet/{z}/{x}/{y}.pbf`
- **Glyphs (Fontstack PBF):** `https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf`
- **Sprites:** `https://tiles.openfreemap.org/sprites/osm-bright`
- **Terms:** 100% free under Open Database License (ODbL). No API key, no registration, no watermarks, unlimited public access.
- **Attribution:** `© OpenStreetMap contributors, OpenFreeMap, Protomaps`

### 2.5 Hybrid Satellite Imagery
- **Provider:** Esri World Imagery (ArcGIS Online)
- **Raster Tile Endpoint:** `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
- **Tile Size:** 256px, maxzoom 19
- **Terms:** Permitted for interactive public web application mapping with standard attribution.
- **Attribution:** `Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community`
- **Hybrid Overlay:** Road network and locality labels are rendered in white with an opaque dark halo (`#000000`, width 2.0) on top of the raster layer.

---

## 3. Theme Switching Architecture

To prevent blank screens and loss of layer state:
1. MapLibre Map is created **ONCE** in React `useEffect`.
2. A single composite style (spec v8) registers all source definitions:
   - `protomaps` (vector PMTiles / OpenFreeMap)
   - `satellite-raster` (Esri World Imagery raster)
3. Layer groups are assigned metadata:
   - `{ metadata: { group: "dark" } }`
   - `{ metadata: { group: "light" } }`
   - `{ metadata: { group: "gray" } }`
   - `{ metadata: { group: "satellite" } }`
   - `{ metadata: { group: "satellite-labels" } }`
4. Switching theme toggles layer visibility:
   ```ts
   map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
   ```
5. Background canvas color is updated via `map.setPaintProperty('bg-solid', 'background-color', tokens.backgroundColor)`.

---

## 4. Network Symbology & Level of Detail (LOD)

Configured in [`config/lod.yaml`](file:///c:/Users/nagra/Desktop/Bwssb1/config/lod.yaml):

| Zoom Level | Visible Features | Symbology / Styling |
| :--- | :--- | :--- |
| **$z < 11$** | BWSSB Division boundaries, division asset count centroid badges, trunk mains ($\ge 600\text{ mm}$). | Supercluster division badges, wide casing, small pipes hidden. |
| **$z \in [11, 14)$** | Pumping stations, WTPs, STPs, GLR balancing tanks, trunk mains ($\ge 600\text{ mm}$). | Full P&ID icons, collision-filtered labels, flow pulses. |
| **$z \in [14, 17)$** | All mains ($\ge 300\text{ mm}$), distribution pipes, inline control valves, electromagnetic flow meters, pressure transmitters at exact chainage $m$. | Inline glyphs rotated to local pipe bearing (`alongLine`, `getBearing`), flow chevrons at $z \ge 15$. |
| **$z \ge 17$** | Site-Plan engineering view for pumping stations and WTPs. | Boundary footprint polygon, suction/discharge manifolds, pump units in a row, isolation valves, instrument tags, 1 Hz rotating impeller glyphs. |

---

## 5. Collapsible P&ID Legend

A compact, collapsible legend sits on the bottom-left of the viewport. It displays:
- Transmission pipe widths and color encodings.
- ISA P&ID asset icons.
- Status rings: Normal (emerald green), Watch (amber), Alert (red), No Data (slate).
- Provenance data tiers: REAL (cyan), SIMULATED (purple), LIVE (emerald).
