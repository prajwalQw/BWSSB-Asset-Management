# Engineering Fixes Report: Map Engine & Telemetry Integrity

**Date:** 2026-10-22  
**Scope:** Map Engine Refactor & Telemetry Honesty Audit

---

## 1. Basemap & Map Engine Fixes

### (a) Carto Watermark & Key Deprecation
- **Problem:** Carto GL raster/vector basemaps now require an authorized API key, resulting in "API KEY REQUIRED" watermarks over the map and failure to resolve place labels.
- **Fix:** Completely purged all Carto (`cartocdn`, `basemaps`), Mapbox, MapTiler, and Stadia URLs from the codebase.
- **New Architecture:**
  - Registered `maplibregl.addProtocol("pmtiles", new Protocol().tile)`.
  - Implemented self-hosted vector tiles with PMTiles (`public/tiles/bengaluru.pmtiles`) generated via `pmtiles extract` with Protomaps basemaps.
  - Sourced OpenFreeMap vector styles as high-availability runtime fallback with zero API keys and no rate limits under ODbL terms.
  - Implemented high-resolution Esri World Imagery raster tiles with permitted attribution and a custom vector hybrid road/place label overlay (white text with dark halo).
  - Ensured locality and neighborhood names are visible starting at zoom 11.

### (b) Blank Map on Theme Switch & Flow Animation Loss
- **Problem:** `map.setStyle()` was called on every theme change. This caused MapLibre to destroy all WebGL sources, layers, and context, dropping Deck.gl layers and breaking requestAnimationFrame animation loops. Switching back to dark resulted in a blank screen.
- **Fix:**
  - MapLibre Map is created **ONCE** in React `useEffect` with StrictMode double-mount protection.
  - A single composite style (spec v8) is constructed at initialization, containing source definitions and tagged layer groups (`group: "light" | "dark" | "gray" | "satellite" | "satellite-labels"`).
  - Theme switching is executed solely via `map.setLayoutProperty(id, 'visibility', ...)` and `map.setPaintProperty()`. `map.setStyle()` is **NEVER** called.
  - Rendered all network assets via `MapboxOverlay` from `@deck.gl/mapbox` with `interleaved: false` (isolated WebGL canvas). Deck.gl layers survive any basemap theme change.
  - Added an error handler with a dismissible toast notification and a fallback background so the map is never blank.

### (c) Ambiguous Marker Circles
- **Problem:** Markers were generic blue, green, and purple circles with no visual distinction between asset types.
- **Fix:** Authored an original P&ID / ISA-5.1 vector icon set packed into an in-memory Icon Atlas:
  - WTP (building with water droplet)
  - Pumping Station (building with pump volute)
  - Pump Unit (motor + volute casing)
  - STP (circle with sewage treatment wave)
  - GLR / Tank (cylinder with level fill)
  - Borewell (vertical bore with downhole pump)
  - Flow Meter (flanged electromagnetic flow tube with transmitter box)
  - Pressure Transmitter (circular gauge dial on pipe stub)
  - Valve (bow-tie; open / closed)
  - Bulk Meter (square chassis with meter dial)
  - Consumer Cluster (house cluster)
- Status is encoded as a dedicated status ring (Normal emerald green, Watch amber, Alert red, No Data grey), plus a tiny text/icon cue.
- Data tier (Real, Simulated, Live) is encoded by corner badges with full legend attribution.
- Added a compact collapsible legend on the bottom-left of the map.

### (d) Zoom Level of Detail & Site-Plan Engineering View
- **Problem:** Pumps, meters, and sensors did not look real or mechanical when zoomed in.
- **Fix:** Configured Level of Detail thresholds in `config/lod.yaml`:
  - $z < 11$: Administrative division boundaries with asset count centroid badges; minor pipes hidden.
  - $z \in [11, 14)$: Transmission mains with collision-filtered labels and P&ID station icons.
  - $z \in [14, 17)$: Inline valve and meter glyphs positioned at exact chainage $m$ along pipes, rotated to pipe bearing; flow direction chevrons at $z \ge 15$.
  - $z \ge 17$: High-detail site-plan view for pumping stations and WTPs:
    - Station building footprint polygon (marked Simulated).
    - Pump units drawn in a row with suction and discharge header manifolds.
    - Suction & discharge valves, flow meter, and pressure transmitter on the discharge line.
    - Instrument tags: "P1 1200 kW", "FM-03 42.1 L/s", "PT-01 6.8 bar".
    - 1 Hz rotating impeller glyph (two-frame animation swap).
    - Status ring per pump unit.

---

## 2. Telemetry Honesty & IGNOAPI Origin Investigation

### Investigation of "95.2 A", "1450 RPM", and "68.5 C":
During the codebase audit, we examined the origin of these specific values:
1. **"95.2 A":**
   - **Source:** Found in hydraulic pump power monitor steady-state evaluations (`rated_current_a = 124.5 A` for the 1200 kW Tataguni 6.6 kV motors; lower 95% confidence bound and partial load evaluated around 95.2 A).
   - **Status:** **SIMULATED**. This is a synthetic 3-phase AC current calculation for a 6.6 kV medium-voltage pump, NOT an authentic live reading from IGNOAPI.
2. **"1450 RPM":**
   - **Source:** Standard 4-pole 50 Hz AC induction motor full-load slip speed (synchronous speed 1500 RPM, slip speed ~1450 RPM).
   - **IGNOAPI Reality:** The actual variable in `ignoAPI/vars.json` is `speed: 360.0 RPM`, which comes from a low-voltage DC drive motor on an automated robot AGV, NOT a 6.6 kV water pump. Any display of 1450 RPM on main pumps was synthetic.
   - **Status:** **SIMULATED**.
3. **"68.5 C":**
   - **Source:** Simulated pump motor winding temperature in the hydraulics studio (hovering around 65–70°C). IGNOAPI has `motor_temp_c: 70.0`.
   - **Status:** **SIMULATED** on main 6.6 kV pump motors; authentic only on the dedicated auxiliary DC panel.

### Actions Taken:
1. **Tier Chips are Per-Element Only:**
   - Deleted the global `<ProvenanceChip tier="REAL" />` from the application header title in `App.tsx`.
2. **Live Feed State & Freshness Synchronization:**
   - Evaluated IGNOAPI connection state against a 3.0-second staleness threshold (`telemetry.stale_threshold_seconds` from `config/lod.yaml` and `config/sensor_map.yaml`).
   - Header status and panel chips read the exact same state: displays **LIVE** (emerald) only when IGNOAPI is connected and fresh ($\Delta t \le 3.0\text{ s}$); otherwise displays **"Feed offline"** (slate) and greys out live telemetry.
3. **True Units on Dedicated Auxiliary Panel:**
   - `voltage_v` ($12.0\text{ V DC}$) and `motor_current_a` ($2.0\text{ A DC}$) appear **ONLY** on the dedicated asset `"Pump control panel (auxiliary supply)"` (`PANEL_TG_AUX_01`) in their true unscaled native units.
   - Main 6.6 kV pump motors (`PUMP_TG_01`, `PUMP_TG_02`, `PUMP_TG_03_STANDBY`), bulk flow meters, and pressure transmitters remain explicitly labeled as **SIMULATED**.
