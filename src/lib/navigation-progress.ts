export type NavigationCoordinate = readonly [lon: number, lat: number];

export interface NavigationPosition {
  lat: number;
  lon: number;
  accuracy?: number;
}

export interface NavigationProgressStep {
  location: NavigationCoordinate;
  /** Global indices in the flattened route geometry, including across legs. */
  geometry_start_index?: number;
  geometry_end_index?: number;
}

type Point = { x: number; y: number };
type Segment = { from: Point; to: Point; length: number; offset: number };
type Projection = { distance: number; along: number };

const METERS_PER_RADIAN = 6_371_000;
const RADIANS_PER_DEGREE = Math.PI / 180;
const MAX_ACCURACY_METERS = 75;

function validCoordinate(point: NavigationCoordinate) {
  return Number.isFinite(point[0]) && Number.isFinite(point[1]);
}

/**
 * Advance from a fix on a route segment, even if intermediate turns were missed.
 * Poor/off-route fixes leave progress unchanged. At crossings, prefer the earliest
 * plausible forward segment rather than jumping to a later pass through it.
 * This only tracks progress; it does not reroute or verify entrances or access.
 */
export function advanceNavigationStep(
  position: NavigationPosition,
  coordinates: readonly NavigationCoordinate[],
  steps: readonly NavigationProgressStep[],
  currentIndex: number,
): number {
  if (
    !Number.isInteger(currentIndex) || currentIndex < 0 || currentIndex >= steps.length ||
    coordinates.length < 2 ||
    !Number.isFinite(position.lat) || !Number.isFinite(position.lon) ||
    Math.abs(position.lat) > 90 || Math.abs(position.lon) > 180 ||
    (position.accuracy !== undefined && (
      !Number.isFinite(position.accuracy) || position.accuracy < 0 ||
      position.accuracy > MAX_ACCURACY_METERS
    )) ||
    coordinates.some(point => !validCoordinate(point))
  ) return currentIndex;

  // A local tangent plane is sufficient for these bounded Astana walking routes.
  const scaleY = METERS_PER_RADIAN * RADIANS_PER_DEGREE;
  const scaleX = scaleY * Math.cos(position.lat * RADIANS_PER_DEGREE);
  const point = ([lon, lat]: NavigationCoordinate): Point => ({
    x: (lon - position.lon) * scaleX,
    y: (lat - position.lat) * scaleY,
  });
  const geometry = coordinates.map(point);
  const offsets = [0];
  const segments: Segment[] = [];
  for (let index = 0; index < geometry.length - 1; index += 1) {
    const from = geometry[index], to = geometry[index + 1];
    const length = Math.hypot(to.x - from.x, to.y - from.y);
    segments.push({ from, to, length, offset: offsets[index] });
    offsets.push(offsets[index] + length);
  }
  const routeLength = offsets.at(-1)!;
  if (!routeLength) return currentIndex;

  function project(target: Point, from: number, to: number, ambiguity = 0): Projection | undefined {
    const candidates: Projection[] = [];
    let nearest = Infinity;
    for (const segment of segments) {
      if (!segment.length || segment.offset + segment.length < from || segment.offset > to) continue;
      const dx = segment.to.x - segment.from.x, dy = segment.to.y - segment.from.y;
      const minimum = Math.max(0, (from - segment.offset) / segment.length);
      const maximum = Math.min(1, (to - segment.offset) / segment.length);
      const fraction = Math.max(minimum, Math.min(maximum,
        ((target.x - segment.from.x) * dx + (target.y - segment.from.y) * dy) / segment.length ** 2,
      ));
      const distance = Math.hypot(target.x - segment.from.x - fraction * dx,
        target.y - segment.from.y - fraction * dy);
      const projection = { distance, along: segment.offset + fraction * segment.length };
      nearest = Math.min(nearest, distance);
      candidates.push(projection);
    }
    // Segments are ordered, so this also resolves equal-distance crossings forward
    // from the current step without choosing a distant future occurrence.
    return candidates.find(candidate => candidate.distance <= nearest + ambiguity + 0.001);
  }

  const validIndex = (index: number | undefined): index is number =>
    index !== undefined && Number.isInteger(index) && index >= 0 && index < offsets.length;
  const starts: number[] = [];
  for (const step of steps) {
    const previous = starts.at(-1) ?? 0;
    if (validIndex(step.geometry_start_index)) {
      starts.push(Math.max(previous, offsets[step.geometry_start_index]));
    } else {
      if (!validCoordinate(step.location)) return currentIndex;
      const end = validIndex(step.geometry_end_index)
        ? Math.max(previous, offsets[step.geometry_end_index]) : routeLength;
      const projected = project(point(step.location), previous, end);
      if (!projected) return currentIndex;
      starts.push(Math.max(previous, projected.along));
    }
  }

  const accuracy = position.accuracy ?? 10;
  const projected = project({ x: 0, y: 0 }, starts[currentIndex], routeLength,
    Math.max(2, Math.min(accuracy / 2, 10)));
  const routeTolerance = Math.max(20, Math.min(accuracy, 35));
  if (!projected || projected.distance > routeTolerance) return currentIndex;

  let nextIndex = currentIndex;
  for (let index = currentIndex + 1; index < starts.length; index += 1) {
    if (starts[index] > projected.along + 0.01) break;
    nextIndex = index;
  }
  return nextIndex;
}
