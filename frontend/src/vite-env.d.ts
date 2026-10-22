/// <reference types="vite/client" />

declare module 'maplibre-gl' {
  const content: any;
  export type StyleSpecification = any;
  export type LayerSpecification = any;
  export type Map = any;
  export type GeoJSONSource = any;
  export type NavigationControl = any;
  export type ScaleControl = any;
  export default content;
}

declare namespace maplibregl {
  type Map = any;
  type GeoJSONSource = any;
  type NavigationControl = any;
  type ScaleControl = any;
  type StyleSpecification = any;
  type LayerSpecification = any;
}

declare module '@deck.gl/core' {
  export const Deck: any;
  export const Layer: any;
  export const CompositeLayer: any;
}

declare module '@deck.gl/layers' {
  export const PathLayer: any;
  export const IconLayer: any;
  export const TextLayer: any;
  export const PolygonLayer: any;
  export const ScatterplotLayer: any;
  export const GeoJsonLayer: any;
}

declare module '@deck.gl/geo-layers' {
  export const TripsLayer: any;
}

declare module '@deck.gl/mapbox' {
  export class MapboxOverlay {
    constructor(props?: any);
    setProps(props: any): void;
    finalize(): void;
  }
}

declare module '*.css' {
  const content: any;
  export default content;
}
