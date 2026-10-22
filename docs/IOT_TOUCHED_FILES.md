# Touched Existing Files Register

Every touched existing file is listed below with the exact reason for the change, adhering strictly to Rule 0.3 and Rule 0.4.

| File Path | Change Category (Rule 0.3) | Exact Reason & Scope | Lines Changed |
|---|---|---|---|
| `backend/app/main.py` | (a) Mount new API router & Server Lifecycle | Imported `iot_router`, `IOT_ENABLED`, and `sim_engine`. Registered `app.include_router(iot_router)`. In `lifespan()`, initialized asynchronous simulation tick loop when `IOT_ENABLED` is true; set `reload=False` to prevent state wiping. | +11 lines |
| `frontend/src/types/index.ts` | (e) Alert list adapter support | Added optional field `source?: 'IOT' \| string;` to `AlertItem` interface to support provenance tagging of IoT alarms without altering existing schema. | +1 line |
| `frontend/src/components/topbar/TopBar.tsx` | (b) Top bar "GIS \| IoT" switch | Added `activeModule?: 'GIS' \| 'IOT'` and `onModuleChange?: (module: 'GIS' \| 'IOT') => void` to `TopBarProps`. Rendered segmented switch next to brand title. | +31 lines |
| `frontend/src/App.tsx` | (b) Route `/iot` & Single Map/SSE Lifecycle | Added route sync for `/iot` and popstate listener; mounted single persistent `<DigitalTwinMap activeModule={activeModule} />` shared by both GIS and IoT workstations so WebGL context and network features are never lost when toggling between GIS and IoT; wrapped app with single `IoTStreamProvider`. | +80 lines |
| `frontend/src/components/map/DigitalTwinMap.tsx` | Map Lifecycle & Resilience | Added `activeModule?: 'GIS' \| 'IOT'` prop forwarding to `buildDeckLayers`; module-level dataset caching and `AbortController` 2.5s timeout on API fetches to prevent stalls when switching tabs; wired `onClose` to `MapLegend`. | +32 lines |
| `frontend/src/components/map/MapLegend.tsx` | UI Legend Symbology | Defaulted `isOpen` to `true` so asset symbology (pump, pumping station, tanks, etc.) displays immediately when opened; added `onClose` button and cleaned styling. | +22 lines |
| `frontend/src/map/deckOverlay.ts` | (c) Map layer registry & Context Dimming | Imported `layerRegistry` and invoked `layerRegistry.getAllLayers(props)` right before `return layers;`. Added `activeModule` to `DeckOverlayProps`; dimmed GIS pipe casing and core to 35% opacity when `activeModule === 'IOT'`; guarded GIS PID station icons from duplicating live IoT layers. | +14 lines |
| `frontend/src/components/panels/RightInspector.tsx` | (d) Section registry & (Rule 0.7) Empty attributes | Added `sectionRegistry.renderSection(asset, onClose, onZoomTo)` check for dynamic IoT inspector tabs; replaced empty attribute values with `"Not published"` instead of blanks. | +7 lines |
| `frontend/src/components/panels/AdminDrawer.tsx` | (8) Additive Admin sections | Added `'iot'` option to `activeSection` state, added "IoT System" tab button, and rendered `<IoTAdminSections />` when `'iot'` is selected. | +8 lines |

## Verification Guarantee
- No existing files were renamed.
- No existing feature code or logic was deleted.
- No existing API response contracts or schemas were altered.
- All modifications are strictly additive and guarded by feature flags.
