/**
 * P&ID and ISA-5.1 Industrial Symbology Atlas Generator
 * Generates original vector icons packed into an atlas for deck.gl IconLayer.
 */

export interface IconBounds {
  x: number;
  y: number;
  width: number;
  height: number;
  anchorX: number;
  anchorY: number;
  mask?: boolean;
}

export type AssetIconType =
  | 'wtp'
  | 'pumping_station'
  | 'pump_unit'
  | 'pump_impeller_0'
  | 'pump_impeller_1'
  | 'stp'
  | 'glr_tank'
  | 'borewell'
  | 'flow_meter'
  | 'pressure_transmitter'
  | 'valve_open'
  | 'valve_closed'
  | 'bulk_meter'
  | 'consumer_cluster'
  | 'chevron';

const ICON_SIZE = 64;

/**
 * Draws an ISA-5.1 / P&ID vector asset icon on a 2D canvas context.
 */
function drawAssetSymbol(
  ctx: CanvasRenderingContext2D,
  type: AssetIconType,
  x: number,
  y: number,
  size: number
) {
  ctx.save();
  ctx.translate(x, y);

  const cx = size / 2;
  const cy = size / 2;

  // Outer symbol circle backing
  ctx.fillStyle = '#0f172a';
  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 2.5;

  switch (type) {
    case 'wtp': {
      // Building with water droplet
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Industrial building roof & base
      ctx.fillStyle = '#38bdf8';
      ctx.beginPath();
      ctx.moveTo(cx - 16, cy + 14);
      ctx.lineTo(cx - 16, cy - 2);
      ctx.lineTo(cx, cy - 14);
      ctx.lineTo(cx + 16, cy - 2);
      ctx.lineTo(cx + 16, cy + 14);
      ctx.closePath();
      ctx.fill();

      // Droplet inside building
      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.moveTo(cx, cy - 8);
      ctx.quadraticCurveTo(cx - 7, cy + 3, cx, cy + 9);
      ctx.quadraticCurveTo(cx + 7, cy + 3, cx, cy - 8);
      ctx.closePath();
      ctx.fill();
      break;
    }

    case 'pumping_station': {
      // Building with pump volute glyph
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Base building
      ctx.fillStyle = '#10b981';
      ctx.fillRect(cx - 14, cy - 2, 28, 16);

      // Centrifugal pump volute
      ctx.beginPath();
      ctx.arc(cx, cy - 4, 10, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Discharge nozzle
      ctx.fillRect(cx + 4, cy - 14, 6, 8);
      break;
    }

    case 'pump_unit': {
      // Motor cylinder + Volute casing
      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Motor rectangle
      ctx.fillStyle = '#3b82f6';
      ctx.fillRect(cx - 18, cy - 8, 16, 16);

      // Shaft coupling
      ctx.fillStyle = '#94a3b8';
      ctx.fillRect(cx - 2, cy - 4, 4, 8);

      // Volute casing circle
      ctx.beginPath();
      ctx.arc(cx + 10, cy, 9, 0, Math.PI * 2);
      ctx.fillStyle = '#10b981';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Tangential discharge port
      ctx.fillStyle = '#10b981';
      ctx.fillRect(cx + 7, cy - 16, 6, 8);
      break;
    }

    case 'pump_impeller_0': {
      // 4-blade impeller at 0 deg
      ctx.beginPath();
      ctx.arc(cx, cy, 24, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(cx - 14, cy);
      ctx.lineTo(cx + 14, cy);
      ctx.moveTo(cx, cy - 14);
      ctx.lineTo(cx, cy + 14);
      ctx.stroke();

      // Central hub
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#06b6d4';
      ctx.fill();
      break;
    }

    case 'pump_impeller_1': {
      // 4-blade impeller rotated 45 deg (for 1Hz rotation animation)
      ctx.beginPath();
      ctx.arc(cx, cy, 24, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(cx - 10, cy - 10);
      ctx.lineTo(cx + 10, cy + 10);
      ctx.moveTo(cx - 10, cy + 10);
      ctx.lineTo(cx + 10, cy - 10);
      ctx.stroke();

      // Central hub
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#06b6d4';
      ctx.fill();
      break;
    }

    case 'stp': {
      // Circle with sewage treatment wave
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Waves
      ctx.strokeStyle = '#c084fc';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx - 16, cy - 4);
      ctx.quadraticCurveTo(cx - 8, cy - 12, cx, cy - 4);
      ctx.quadraticCurveTo(cx + 8, cy + 4, cx + 16, cy - 4);
      ctx.moveTo(cx - 16, cy + 6);
      ctx.quadraticCurveTo(cx - 8, cy - 2, cx, cy + 6);
      ctx.quadraticCurveTo(cx + 8, cy + 14, cx + 16, cy + 6);
      ctx.stroke();
      break;
    }

    case 'glr_tank': {
      // Cylinder with level fill
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Cylinder outline
      ctx.strokeStyle = '#94a3b8';
      ctx.lineWidth = 2;
      ctx.strokeRect(cx - 14, cy - 14, 28, 28);

      // Water level fill (approx 70%)
      ctx.fillStyle = '#0284c7';
      ctx.fillRect(cx - 13, cy - 4, 26, 17);

      // Level tick marks
      ctx.strokeStyle = '#ffffff';
      ctx.beginPath();
      ctx.moveTo(cx + 8, cy - 4);
      ctx.lineTo(cx + 13, cy - 4);
      ctx.moveTo(cx + 8, cy + 3);
      ctx.lineTo(cx + 13, cy + 3);
      ctx.stroke();
      break;
    }

    case 'borewell': {
      // Vertical bore with pump
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Well head surface plate
      ctx.fillStyle = '#64748b';
      ctx.fillRect(cx - 14, cy - 14, 28, 5);

      // Vertical casing pipe
      ctx.strokeStyle = '#94a3b8';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx, cy - 10);
      ctx.lineTo(cx, cy + 14);
      ctx.stroke();

      // Submersible pump capsule
      ctx.fillStyle = '#3b82f6';
      ctx.fillRect(cx - 5, cy + 2, 10, 12);
      break;
    }

    case 'flow_meter': {
      // Flanged electromagnetic flow tube + transmitter box
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Pipe spool tube
      ctx.fillStyle = '#475569';
      ctx.fillRect(cx - 16, cy + 2, 32, 8);

      // Left and right pipe flanges
      ctx.fillStyle = '#94a3b8';
      ctx.fillRect(cx - 18, cy - 1, 4, 14);
      ctx.fillRect(cx + 14, cy - 1, 4, 14);

      // Electronic transmitter box
      ctx.fillStyle = '#06b6d4';
      ctx.fillRect(cx - 7, cy - 14, 14, 12);

      // Stalk
      ctx.fillStyle = '#cbd5e1';
      ctx.fillRect(cx - 2, cy - 2, 4, 4);
      break;
    }

    case 'pressure_transmitter': {
      // Circular gauge dial on vertical pipe stub
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Pipe stub
      ctx.fillStyle = '#94a3b8';
      ctx.fillRect(cx - 2, cy + 6, 4, 10);

      // Circular gauge dial
      ctx.beginPath();
      ctx.arc(cx, cy - 4, 11, 0, Math.PI * 2);
      ctx.fillStyle = '#ffffff';
      ctx.fill();
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Gauge needle pointing at pressure
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy - 4);
      ctx.lineTo(cx + 6, cy - 9);
      ctx.stroke();
      break;
    }

    case 'valve_open': {
      // Bow-tie valve (open / hollow)
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Left triangle
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(cx - 14, cy - 10);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx - 14, cy + 10);
      ctx.closePath();
      ctx.stroke();

      // Right triangle
      ctx.beginPath();
      ctx.moveTo(cx + 14, cy - 10);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx + 14, cy + 10);
      ctx.closePath();
      ctx.stroke();

      // Valve actuator stem & handwheel
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx, cy - 12);
      ctx.stroke();
      ctx.strokeRect(cx - 6, cy - 15, 12, 3);
      break;
    }

    case 'valve_closed': {
      // Bow-tie valve (closed / solid fill)
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Left triangle filled
      ctx.fillStyle = '#ef4444';
      ctx.beginPath();
      ctx.moveTo(cx - 14, cy - 10);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx - 14, cy + 10);
      ctx.closePath();
      ctx.fill();

      // Right triangle filled
      ctx.beginPath();
      ctx.moveTo(cx + 14, cy - 10);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx + 14, cy + 10);
      ctx.closePath();
      ctx.fill();

      // Valve actuator stem & handwheel
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx, cy - 12);
      ctx.stroke();
      ctx.strokeRect(cx - 6, cy - 15, 12, 3);
      break;
    }

    case 'bulk_meter': {
      // Square chassis with meter dial
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      ctx.fillStyle = '#1e293b';
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 2;
      ctx.strokeRect(cx - 12, cy - 12, 24, 24);
      ctx.fillRect(cx - 11, cy - 11, 22, 22);

      // Meter register counter
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(cx - 8, cy - 5, 16, 10);
      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 8px monospace';
      ctx.fillText('042', cx - 7, cy + 3);
      break;
    }

    case 'consumer_cluster': {
      // Cluster of 3 houses
      ctx.beginPath();
      ctx.arc(cx, cy, 26, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#818cf8';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      ctx.fillStyle = '#818cf8';
      // Center house
      ctx.beginPath();
      ctx.moveTo(cx - 6, cy + 8);
      ctx.lineTo(cx - 6, cy - 2);
      ctx.lineTo(cx, cy - 9);
      ctx.lineTo(cx + 6, cy - 2);
      ctx.lineTo(cx + 6, cy + 8);
      ctx.closePath();
      ctx.fill();

      // Left house
      ctx.beginPath();
      ctx.moveTo(cx - 15, cy + 12);
      ctx.lineTo(cx - 15, cy + 3);
      ctx.lineTo(cx - 10, cy - 2);
      ctx.lineTo(cx - 5, cy + 3);
      ctx.lineTo(cx - 5, cy + 12);
      ctx.closePath();
      ctx.fill();

      // Right house
      ctx.beginPath();
      ctx.moveTo(cx + 5, cy + 12);
      ctx.lineTo(cx + 5, cy + 3);
      ctx.lineTo(cx + 10, cy - 2);
      ctx.lineTo(cx + 15, cy + 3);
      ctx.lineTo(cx + 15, cy + 12);
      ctx.closePath();
      ctx.fill();
      break;
    }

    case 'chevron': {
      // Direction chevron for high-zoom flow vectors
      ctx.fillStyle = '#ffffff';
      ctx.strokeStyle = '#0284c7';
      ctx.lineWidth = 1.5;

      ctx.beginPath();
      ctx.moveTo(cx - 14, cy + 10);
      ctx.lineTo(cx, cy - 12);
      ctx.lineTo(cx + 14, cy + 10);
      ctx.lineTo(cx, cy - 2);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      break;
    }
  }

  ctx.restore();
}

/**
 * Builds the complete Icon Atlas in-memory and returns the Atlas Image and IconMapping table.
 */
export function buildIconAtlas(): {
  atlasUrl: string;
  atlasImage: HTMLCanvasElement;
  mapping: Record<string, IconBounds>;
} {
  const iconTypes: AssetIconType[] = [
    'wtp',
    'pumping_station',
    'pump_unit',
    'pump_impeller_0',
    'pump_impeller_1',
    'stp',
    'glr_tank',
    'borewell',
    'flow_meter',
    'pressure_transmitter',
    'valve_open',
    'valve_closed',
    'bulk_meter',
    'consumer_cluster',
    'chevron',
  ];

  const cols = 4;
  const rows = Math.ceil(iconTypes.length / cols);
  const canvasWidth = cols * ICON_SIZE;
  const canvasHeight = rows * ICON_SIZE;

  const canvas = document.createElement('canvas');
  canvas.width = canvasWidth;
  canvas.height = canvasHeight;
  const ctx = canvas.getContext('2d');

  const mapping: Record<string, IconBounds> = {};

  if (ctx) {
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);

    iconTypes.forEach((type, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);
      const x = col * ICON_SIZE;
      const y = row * ICON_SIZE;

      drawAssetSymbol(ctx, type, x, y, ICON_SIZE);

      mapping[type] = {
        x,
        y,
        width: ICON_SIZE,
        height: ICON_SIZE,
        anchorX: ICON_SIZE / 2,
        anchorY: ICON_SIZE / 2,
        mask: false,
      };
    });
  }

  const atlasUrl = canvas.toDataURL('image/png');

  return {
    atlasUrl,
    atlasImage: canvas,
    mapping,
  };
}
