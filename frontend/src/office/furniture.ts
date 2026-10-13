import { box, ellipse, iso, line, plane, polygon, rounded, shadow, type Context } from './geometry';

export type SceneObject = { depth: number; draw: (c: Context) => void };
const oak: [string, string, string] = ['#c7a17a', '#96704f', '#ae8660'];
const dark: [string, string, string] = ['#62685e', '#373e37', '#495147'];

function desk(c: Context) {
  shadow(c, 7, 2.4, 106, 33);
  for (const [x, y] of [[5.05, 1.3], [8.85, 1.3], [5.05, 3.15], [8.85, 3.15]]) {
    box(c, x, y, .12, .12, 0, 2.02, dark);
    line(c, iso(x, y, .12), iso(x, y, 1.96), '#85877a', 1);
  }
  box(c, 4.8, 1.1, 4.4, 2.35, 2.03, .16, oak);
  for (let i = 0; i < 7; i++) line(c, iso(4.95, 1.26 + i * .3, 2.195), iso(9.07, 1.26 + i * .3, 2.195), 'rgba(255,240,212,.18)', .55);
  plane(c, 6.1, 2, 2.4, 1.15, 2.2, '#6b7569');
  plane(c, 6.72, 1.65, .75, .46, 2.2, '#333d37');
  box(c, 7.02, 1.76, .12, .12, 2.21, .39, dark);
  // Monitor is a thin vertical slab, facing into the room, not a flat floor tile.
  box(c, 6.05, 1.72, 2.52, .11, 2.58, 1.36, ['#46514c', '#25312f', '#172422']);
  polygon(c, [iso(6.14, 1.835, 2.68), iso(8.47, 1.835, 2.68), iso(8.47, 1.835, 3.85), iso(6.14, 1.835, 3.85)], '#aec5bd');
  polygon(c, [iso(6.23, 1.84, 2.77), iso(6.82, 1.84, 2.77), iso(6.82, 1.84, 3.74), iso(6.23, 1.84, 3.74)], '#8ca99d');
  for (let i = 0; i < 5; i++) line(c, iso(7, 1.85, 3.58 - i * .14), iso(8.15 - i % 2 * .3, 1.85, 3.58 - i * .14), '#e0e8d9', 1.7);
  line(c, iso(6.2, 1.84, 3.81), iso(8.4, 1.84, 3.81), '#d4e5da', .8);
  // A desk mat, individual keycaps, mouse, notebook and ceramic cup.
  box(c, 6.25, 2.65, 1.65, .42, 2.21, .06, ['#d9d9c9', '#a4aa9a', '#bcc0b0']);
  for (let row = 0; row < 3; row++) for (let col = 0; col < 12; col++) plane(c, 6.32 + col * .126, 2.68 + row * .105, .09, .075, 2.276, '#f2f0e5');
  const mouse = iso(8.17, 2.78, 2.24);
  ellipse(c, ...mouse, 6, 3.5, '#dddcd0', -.45);
  line(c, [mouse[0], mouse[1] - 2], [mouse[0] + 2, mouse[1]], '#a6ac9e', .7);
  box(c, 5.15, 2.1, .68, .87, 2.2, .06, ['#e8dcc0', '#b5a389', '#cec1a3']);
  line(c, iso(5.43, 2.24, 2.28), iso(5.43, 2.81, 2.28), '#9a8065', 1);
  const [cx, cy] = iso(8.82, 2.57, 2.2);
  rounded(c, cx - 5, cy - 13, 10, 13, 3, '#e9e3d1');
  ellipse(c, cx, cy - 12, 5, 2.6, '#b9a993'); ellipse(c, cx, cy - 12, 3.6, 1.6, '#615044');
  c.strokeStyle = '#e9e3d1'; c.lineWidth = 2; c.beginPath(); c.arc(cx + 6, cy - 7, 3, -Math.PI / 2, Math.PI / 2); c.stroke();
  // Brass task lamp and a restrained pool of warm light on the oak.
  const [lx, ly] = iso(5.35, 1.55, 2.2);
  ellipse(c, lx + 10, ly + 8, 25, 10, 'rgba(255,224,160,.19)');
  ellipse(c, lx, ly, 9, 4, '#a18b59');
  line(c, [lx, ly], [lx, ly - 37], '#978256', 3);
  line(c, [lx, ly - 37], [lx + 17, ly - 45], '#b5a074', 3);
  polygon(c, [[lx + 8, ly - 44], [lx + 23, ly - 48], [lx + 29, ly - 36], [lx + 10, ly - 31]], '#697463');
  line(c, [lx + 10, ly - 31], [lx + 29, ly - 36], '#e8d4a3', 2);
}

function shelf(c: Context) {
  shadow(c, .75, 2.9, 55, 24);
  const frame: [string, string, string] = ['#bc9971', '#8c704e', '#a88964'];
  box(c, .27, .85, .08, 3.7, .1, 4.25, frame);
  box(c, .27, .85, .68, .12, .1, 4.25, frame);
  box(c, .27, 4.43, .68, .12, .1, 4.25, frame);
  for (let level = 0; level < 4; level++) {
    const z = .25 + level * 1.02;
    box(c, .28, .85, .68, 3.7, z - .02, .09, oak);
    for (let b = 0; b < 11; b++) {
      const y = 1.12 + b * .27;
      const h = .72 + ((b * 7 + level * 3) % 5) * .035;
      const colors = ['#6e877e', '#c4b78e', '#ad775b', '#c8c8b5', '#787e71'];
      box(c, .5, y, .47, .2, z + .07, h, [colors[b % 5], colors[(b + 1) % 5], colors[b % 5]]);
      line(c, iso(.974, y + .03, z + .22), iso(.974, y + .16, z + .22), '#dac9ac', .65);
      line(c, iso(.974, y + .03, z + h - .02), iso(.974, y + .16, z + h - .02), 'rgba(249,238,213,.4)', .6);
    }
  }
  box(c, .28, .85, .68, 3.7, 4.35, .1, oak);
}

function chair(c: Context) {
  const [x, y] = iso(7.4, 4.25);
  shadow(c, 7.4, 4.25, 24, 10);
  for (let i = 0; i < 5; i++) {
    const angle = i * Math.PI * 2 / 5;
    const end: [number, number] = [x + Math.cos(angle) * 25, y + Math.sin(angle) * 10];
    line(c, [x, y - 5], end, '#525b54', 3); ellipse(c, end[0], end[1] + 1, 3, 2.4, '#303b35');
  }
  line(c, [x, y - 5], [x, y - 27], '#7a857c', 4);
  ellipse(c, x, y - 28, 22, 10, '#475c50'); ellipse(c, x - 1, y - 31, 21, 9, '#6b7d6d');
  rounded(c, x - 21, y - 76, 40, 43, 10, '#4a6053');
  rounded(c, x - 17, y - 74, 32, 34, 8, '#7b8d79');
  for (let i = 0; i < 5; i++) line(c, [x - 13, y - 67 + i * 5], [x + 10, y - 68 + i * 5], '#91a18b', .55);
  for (const sign of [-1, 1]) { line(c, [x + sign * 17, y - 31], [x + sign * 25, y - 45], '#46584c', 3); line(c, [x + sign * 25, y - 45], [x + sign * 13, y - 49], '#6c7c6c', 4); }
}

function sofa(c: Context) {
  shadow(c, 2.55, 8.75, 72, 28);
  for (const [x, y] of [[1.25, 8.12], [3.86, 8.12], [1.25, 9.38], [3.86, 9.38]]) box(c, x, y, .14, .14, .03, .35, oak);
  const fabric: [string, string, string] = ['#c1c6ad', '#8e9b81', '#a3b094'];
  box(c, 1.1, 7.95, 3, 1.75, .36, .58, fabric);
  box(c, 1.1, 7.95, 3, .3, .91, 1.13, fabric);
  for (const x of [1.42, 2.72]) box(c, x, 8.33, 1.26, 1.15, .91, .19, ['#d0d1b9', '#aeb89c', '#bcc4aa']);
  for (const x of [1.07, 3.81]) box(c, x, 8.05, .32, 1.65, .84, .62, fabric);
  box(c, 1.62, 8.27, .65, .22, 1.15, .65, ['#e2cfad', '#cab798', '#d8c7a8']);
  box(c, 2.98, 8.27, .57, .22, 1.15, .58, ['#92a295', '#6f8777', '#829687']);
  line(c, iso(1.45, 9.48, 1.09), iso(3.77, 9.48, 1.09), '#e0dfc7', .7);
}

function table(c: Context) {
  shadow(c, 4.55, 7.65, 32, 15);
  for (const [x, y] of [[3.8, 7], [5, 7], [4.4, 8.25]]) box(c, x, y, .1, .1, 0, .92, oak);
  box(c, 3.65, 6.85, 1.6, 1.65, .92, .12, oak);
  box(c, 3.88, 7.1, .7, .85, 1.04, .1, ['#ede5ce', '#718779', '#8c9c87']);
  box(c, 3.92, 7.14, .65, .79, 1.14, .08, ['#b78b6d', '#926c52', '#a77d61']);
  const [x, y] = iso(4.87, 7.64, 1.05);
  ellipse(c, x, y - 4, 5, 3, '#ede9db'); rounded(c, x - 4, y - 11, 8, 7, 2, '#eeeade'); ellipse(c, x, y - 11, 4, 2, '#887662');
}

function plant(c: Context, x: number, y: number, size: number) {
  const [px, py] = iso(x, y);
  shadow(c, x, y, 20 * size, 9 * size);
  polygon(c, [[px - 15 * size, py - 20 * size], [px + 15 * size, py - 20 * size], [px + 11 * size, py], [px - 11 * size, py]], '#b58a69');
  ellipse(c, px, py - 20 * size, 15 * size, 6 * size, '#d4b491'); ellipse(c, px, py - 21 * size, 11 * size, 4 * size, '#63533c');
  for (let i = 0; i < 9; i++) {
    const a = i * 2.4;
    const ex = px + Math.sin(a) * (19 + i % 3 * 5) * size;
    const ey = py - (34 + i * 6) * size;
    line(c, [px, py - 21 * size], [ex, ey], '#70865d', 1.2 * size);
    ellipse(c, ex, ey, (9 + i % 2 * 3) * size, 5 * size, i % 2 ? '#617d55' : '#80986b', a * .4);
    line(c, [ex - 3 * size, ey + 2 * size], [ex + 3 * size, ey - 2 * size], '#9aad7e', .6 * size);
  }
}

export const furniture: SceneObject[] = [
  { depth: 4.2, draw: shelf },
  { depth: 9.5, draw: desk },
  { depth: 11.7, draw: chair },
  { depth: 12.1, draw: c => plant(c, 10.7, 1.25, 1.15) },
  { depth: 12.2, draw: sofa },
  { depth: 12.3, draw: table },
  { depth: 12.7, draw: c => plant(c, 1.3, 11.2, .9) },
];
