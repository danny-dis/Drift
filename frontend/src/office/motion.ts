import { DESK_SEAT } from './layout.ts';
export type OfficeActivity = 'idle' | 'browsing' | 'writing' | 'reading' | 'thinking' | 'waiting';
export type OfficePoint = { x: number; y: number };
const NODES: OfficePoint[] = [
  { x: 6, y: 5.6 }, { x: 7.4, y: 5.6 }, DESK_SEAT,
  { x: 1.6, y: 5.6 }, { x: 1.6, y: 3.4 }, { x: 1.4, y: 6.4 },
  { x: 6, y: 10.5 }, { x: 2.6, y: 10.5 }, { x: 2.6, y: 8.9 },
];
const EDGES = [[1, 3, 6], [0, 2], [1], [0, 4, 5], [3], [3], [0, 7], [6, 8], [7]];
const STATIONS: Record<OfficeActivity, number> = { idle: 8, browsing: 2, writing: 2, reading: 4, thinking: 5, waiting: 8 };
const distance = (a: OfficePoint, b: OfficePoint) => Math.hypot(a.x - b.x, a.y - b.y);

export function officePosition(activity: OfficeActivity): OfficePoint {
  return { ...NODES[STATIONS[activity]] };
}

export function officeRoute(from: OfficePoint, activity: OfficeActivity): OfficePoint[] {
  const start = NODES.reduce((best, node, i) => distance(node, from) < distance(NODES[best], from) ? i : best, 0);
  const goal = STATIONS[activity];
  const queue = [[start]], seen = new Set([start]);
  while (queue.length) {
    const path = queue.shift()!;
    const end = path[path.length - 1];
    if (end === goal) return path.map(i => ({ ...NODES[i] })).filter(p => distance(p, from) > .001);
    for (const next of EDGES[end]) if (!seen.has(next)) { seen.add(next); queue.push([...path, next]); }
  }
  return [];
}

export function walkStep(from: OfficePoint, to: OfficePoint, deltaMs: number): OfficePoint {
  const d = distance(from, to);
  const step = Number.isFinite(deltaMs) ? Math.max(0, Math.min(100, deltaMs)) * .0016 : 0;
  if (d <= step || d === 0) return { ...to };
  return { x: from.x + (to.x - from.x) * step / d, y: from.y + (to.y - from.y) * step / d };
}
