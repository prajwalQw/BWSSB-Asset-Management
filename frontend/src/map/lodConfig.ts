/**
 * Level of Detail (LOD) & Engine Configuration
 * Sourced directly from config/lod.yaml
 */

export interface BoundingBox {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
  paddingPercent: number;
}

export interface ZoomThresholds {
  superclusterMaxZoom: number;
  trunkMainsMinZoom: number;
  trunkMainsMaxZoom: number;
  allMainsMinZoom: number;
  allMainsMaxZoom: number;
  chevronsMinZoom: number;
  sitePlanMinZoom: number;
}

export interface CameraShortcut {
  name: string;
  description: string;
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface SitePlanPumpUnit {
  id: string;
  tag: string;
  offset_m: [number, number];
  rotation_deg: number;
  rated_kw: number;
  rated_current_a: number;
  rated_voltage_v: number;
  suction_valve_offset_m: [number, number];
  discharge_valve_offset_m: [number, number];
}

export interface SitePlanConfig {
  station_id: string;
  name: string;
  origin: [number, number];
  footprint: {
    width_m: number;
    length_m: number;
    rotation_deg: number;
    is_simulated: boolean;
  };
  suction_header: {
    offset_start_m: [number, number];
    offset_end_m: [number, number];
    diameter_mm: number;
  };
  discharge_header: {
    offset_start_m: [number, number];
    offset_end_m: [number, number];
    diameter_mm: number;
  };
  pump_units: SitePlanPumpUnit[];
  instrumentation: {
    flow_meter: {
      id: string;
      tag: string;
      offset_m: [number, number];
    };
    pressure_transmitter: {
      id: string;
      tag: string;
      offset_m: [number, number];
    };
  };
}

export const LOD_CONFIG = {
  boundingBox: {
    minLon: 77.0300,
    minLat: 12.1570,
    maxLon: 77.8700,
    maxLat: 13.2730,
    paddingPercent: 10.0,
  } as BoundingBox,

  zoomThresholds: {
    superclusterMaxZoom: 11.0,
    trunkMainsMinZoom: 11.0,
    trunkMainsMaxZoom: 14.0,
    allMainsMinZoom: 14.0,
    allMainsMaxZoom: 17.0,
    chevronsMinZoom: 15.0,
    sitePlanMinZoom: 17.0,
  } as ZoomThresholds,

  pipeClasses: {
    trunk: {
      minDiameterMm: 600,
      casingWidthMeters: 4.5,
      coreWidthMeters: 2.8,
      minPixels: 3.5,
      maxPixels: 14.0,
    },
    mains: {
      minDiameterMm: 300,
      maxDiameterMm: 600,
      casingWidthMeters: 3.2,
      coreWidthMeters: 1.8,
      minPixels: 2.5,
      maxPixels: 10.0,
    },
    distribution: {
      maxDiameterMm: 300,
      casingWidthMeters: 2.0,
      coreWidthMeters: 1.2,
      minPixels: 1.5,
      maxPixels: 6.0,
    },
  },

  flowAnimation: {
    trailLength: 120.0,
    fadeTrail: true,
    minZoom: 11.0,
    defaultVelocityMps: 1.2,
    chevronIntervalM: 90.0,
    impellerRotationHz: 1.0,
  },

  telemetry: {
    staleThresholdSeconds: 3.0,
    pollIntervalSeconds: 0.5,
  },

  cameraShortcuts: {
    city: {
      name: "City View",
      description: "Greater Bengaluru Metropolitan Overview (z=11.2)",
      center: [77.5946, 12.9716],
      zoom: 11.2,
      pitch: 30,
      bearing: 0,
    },
    tataguni: {
      name: "Tataguni Corridor",
      description: "South-Central Transmission Corridor (z=14.2)",
      center: [77.5300, 12.8750],
      zoom: 14.2,
      pitch: 42,
      bearing: -12,
    },
    jayanagar: {
      name: "Jayanagar DMA",
      description: "Distribution Management Area & Local Mains (z=15.8)",
      center: [77.5750, 12.9350],
      zoom: 15.8,
      pitch: 48,
      bearing: -20,
    },
    tataguni_site: {
      name: "Tataguni Site Plan",
      description: "Terminal Pumping Station Electromechanical Layout (z=17.5)",
      center: [77.5148, 12.8690],
      zoom: 17.5,
      pitch: 50,
      bearing: -22,
    },
    tkhalli_site: {
      name: "TK Halli WTP Site",
      description: "Torekadanahalli Water Treatment Works (z=17.5)",
      center: [77.1650, 12.3150],
      zoom: 17.5,
      pitch: 45,
      bearing: -15,
    },
  } as Record<string, CameraShortcut>,

  sitePlans: {
    PS_TATAGUNI_TERMINAL: {
      station_id: "PS_TATAGUNI_TERMINAL",
      name: "Tataguni Terminal Pumping Station",
      origin: [77.5148, 12.8690],
      footprint: {
        width_m: 60.0,
        length_m: 35.0,
        rotation_deg: 35.0,
        is_simulated: true,
      },
      suction_header: {
        offset_start_m: [-20.0, -8.0],
        offset_end_m: [20.0, -8.0],
        diameter_mm: 1200,
      },
      discharge_header: {
        offset_start_m: [-20.0, 12.0],
        offset_end_m: [20.0, 12.0],
        diameter_mm: 1000,
      },
      pump_units: [
        {
          id: "P1",
          tag: "P1 1200 kW",
          offset_m: [-12.0, 2.0],
          rotation_deg: 90.0,
          rated_kw: 1200,
          rated_current_a: 124.5,
          rated_voltage_v: 6600,
          suction_valve_offset_m: [-12.0, -4.0],
          discharge_valve_offset_m: [-12.0, 7.0],
        },
        {
          id: "P2",
          tag: "P2 1200 kW",
          offset_m: [0.0, 2.0],
          rotation_deg: 90.0,
          rated_kw: 1200,
          rated_current_a: 124.5,
          rated_voltage_v: 6600,
          suction_valve_offset_m: [0.0, -4.0],
          discharge_valve_offset_m: [0.0, 7.0],
        },
        {
          id: "P3",
          tag: "P3 1200 kW (Standby)",
          offset_m: [12.0, 2.0],
          rotation_deg: 90.0,
          rated_kw: 1200,
          rated_current_a: 124.5,
          rated_voltage_v: 6600,
          suction_valve_offset_m: [12.0, -4.0],
          discharge_valve_offset_m: [12.0, 7.0],
        },
      ],
      instrumentation: {
        flow_meter: {
          id: "FM-03",
          tag: "FM-03 42.1 L/s",
          offset_m: [24.0, 12.0],
        },
        pressure_transmitter: {
          id: "PT-01",
          tag: "PT-01 6.8 bar",
          offset_m: [-22.0, 12.0],
        },
      },
    } as SitePlanConfig,
  } as Record<string, SitePlanConfig>,
};
