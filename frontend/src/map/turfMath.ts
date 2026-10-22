/**
 * Geodesic and spherical math utilities
 * Equivalent to Turf.js along, bearing, and destination point algorithms.
 */

const EARTH_RADIUS_METERS = 6371008.8;

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function toDegrees(radians: number): number {
  return (radians * 180) / Math.PI;
}

/**
 * Calculates geodesic distance between two [lon, lat] coordinates in meters using the Haversine formula.
 */
export function haversineDistance(
  p1: [number, number],
  p2: [number, number]
): number {
  const [lon1, lat1] = p1;
  const [lon2, lat2] = p2;

  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const rLat1 = toRadians(lat1);
  const rLat2 = toRadians(lat2);

  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(rLat1) * Math.cos(rLat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return EARTH_RADIUS_METERS * c;
}

/**
 * Calculates geographic bearing (angle clockwise from true North, 0 to 360 degrees) from p1 to p2.
 */
export function getBearing(
  p1: [number, number],
  p2: [number, number]
): number {
  const [lon1, lat1] = p1;
  const [lon2, lat2] = p2;

  const rLat1 = toRadians(lat1);
  const rLat2 = toRadians(lat2);
  const dLon = toRadians(lon2 - lon1);

  const y = Math.sin(dLon) * Math.cos(rLat2);
  const x =
    Math.cos(rLat1) * Math.sin(rLat2) -
    Math.sin(rLat1) * Math.cos(rLat2) * Math.cos(dLon);

  const brng = toDegrees(Math.atan2(y, x));
  return (brng + 360) % 360;
}

/**
 * Calculates a point at a specific chainage distance along a LineString [lon, lat][]
 * Returns interpolated [lon, lat] point and the segment bearing at that chainage.
 */
export function alongLine(
  coords: [number, number][],
  chainageMeters: number
): { coord: [number, number]; bearing: number } {
  if (!coords || coords.length === 0) {
    return { coord: [77.5946, 12.9716], bearing: 0 };
  }
  if (coords.length === 1) {
    return { coord: coords[0], bearing: 0 };
  }

  let accumulatedDist = 0;

  for (let i = 0; i < coords.length - 1; i++) {
    const p1 = coords[i];
    const p2 = coords[i + 1];
    const segDist = haversineDistance(p1, p2);

    if (accumulatedDist + segDist >= chainageMeters || i === coords.length - 2) {
      const remaining = Math.max(0, chainageMeters - accumulatedDist);
      const fraction = segDist > 0 ? Math.min(1.0, remaining / segDist) : 0;
      const interpLon = p1[0] + fraction * (p2[0] - p1[0]);
      const interpLat = p1[1] + fraction * (p2[1] - p1[1]);
      const bearing = getBearing(p1, p2);
      return {
        coord: [interpLon, interpLat],
        bearing,
      };
    }

    accumulatedDist += segDist;
  }

  const last = coords[coords.length - 1];
  const secondLast = coords[coords.length - 2];
  return { coord: last, bearing: getBearing(secondLast, last) };
}

/**
 * Projects a local Cartesian offset [dx, dy] in meters (relative to an origin point and site rotation)
 * to geographic [lon, lat].
 * dx = right/east relative to site orientation, dy = forward/north relative to site orientation.
 */
export function offsetMetersToLngLat(
  origin: [number, number],
  offsetM: [number, number],
  siteRotationDeg: number = 0
): [number, number] {
  const [originLon, originLat] = origin;
  const [dx, dy] = offsetM;

  // Rotate offset by site rotation angle
  const rad = toRadians(siteRotationDeg);
  const rotatedEast = dx * Math.cos(rad) - dy * Math.sin(rad);
  const rotatedNorth = dx * Math.sin(rad) + dy * Math.cos(rad);

  const latRad = toRadians(originLat);
  const metersPerDegLat = (Math.PI * EARTH_RADIUS_METERS) / 180.0;
  const metersPerDegLon = metersPerDegLat * Math.cos(latRad);

  const deltaLat = rotatedNorth / metersPerDegLat;
  const deltaLon = rotatedEast / metersPerDegLon;

  return [originLon + deltaLon, originLat + deltaLat];
}
