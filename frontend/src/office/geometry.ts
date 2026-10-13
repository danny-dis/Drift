export const WIDTH = 1000;
export const HEIGHT = 760;
export type Point = [number, number];
export type Context = CanvasRenderingContext2D;
export const iso = (x: number, y: number, z = 0): Point => [500 + (x - y) * 34, 235 + (x + y) * 18 - z * 34];

export function polygon(c: Context, points: Point[], fill: string, stroke?: string) {
  c.beginPath();
  points.forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y));
  c.closePath(); c.fillStyle = fill; c.fill();
  if (stroke) { c.strokeStyle = stroke; c.lineWidth = 0.7; c.stroke(); }
}
export function plane(c: Context, x: number, y: number, w: number, d: number, z: number, color: string, stroke?: string) {
  polygon(c, [iso(x, y, z), iso(x + w, y, z), iso(x + w, y + d, z), iso(x, y + d, z)], color, stroke);
}
export function box(c: Context, x: number, y: number, w: number, d: number, z: number, h: number, colors: [string, string, string]) {
  polygon(c, [iso(x, y + d, z), iso(x + w, y + d, z), iso(x + w, y + d, z + h), iso(x, y + d, z + h)], colors[1]);
  polygon(c, [iso(x + w, y, z), iso(x + w, y + d, z), iso(x + w, y + d, z + h), iso(x + w, y, z + h)], colors[2]);
  plane(c, x, y, w, d, z + h, colors[0]);
}
export function line(c: Context, a: Point, b: Point, color: string, width = 1) {
  c.beginPath(); c.moveTo(...a); c.lineTo(...b); c.strokeStyle = color; c.lineWidth = width; c.lineCap = 'round'; c.stroke();
}
export function ellipse(c: Context, x: number, y: number, rx: number, ry: number, color: string, rotation = 0) {
  c.beginPath(); c.ellipse(x, y, rx, ry, rotation, 0, Math.PI * 2); c.fillStyle = color; c.fill();
}
export function shadow(c: Context, x: number, y: number, rx: number, ry: number) {
  const [px, py] = iso(x, y);
  for (let i = 4; i > 0; i--) ellipse(c, px + 9, py + 6, rx + i * 3, ry + i * 1.5, 'rgba(41,34,26,.035)');
  ellipse(c, px, py + 2, rx, ry, 'rgba(41,34,26,.13)');
}
export function rounded(c: Context, x: number, y: number, w: number, h: number, r: number, color: string) {
  c.beginPath(); c.roundRect(x, y, w, h, r); c.fillStyle = color; c.fill();
}
