import { box, ellipse, iso, line, plane, polygon, type Context } from './geometry';

function windowWall(c: Context) {
  const wall = (y: number, z: number) => iso(0, y, z);
  polygon(c, [wall(5.2, 1.8), wall(10.5, 1.8), wall(10.5, 4.6), wall(5.2, 4.6)], '#b4a88e');
  polygon(c, [wall(5.35, 1.95), wall(10.35, 1.95), wall(10.35, 4.45), wall(5.35, 4.45)], '#cbdde0');
  // A distant treeline, intentionally quiet rather than a second focal point.
  for (let i = 0; i < 14; i++) {
    const y = 5.5 + i * .35;
    polygon(c, [wall(y, 1.97), wall(y + .34, 1.97), wall(y + .34, 2.3 + Math.sin(i * 2) * .13), wall(y, 2.4)], '#adbec0');
  }
  for (const y of [5.35, 7.85, 10.35]) line(c, wall(y, 1.95), wall(y, 4.45), '#f7f6ee', 5);
  line(c, wall(5.35, 3.1), wall(10.35, 3.1), '#f7f6ee', 4);
  polygon(c, [wall(5.35, 4.35), wall(7.6, 4.35), wall(9.3, 2), wall(7.6, 2)], 'rgba(255,255,255,.18)');
  box(c, 0, 5.12, .32, 5.55, 1.75, .12, ['#f7f3e8', '#c6bcaa', '#d8cfbf']);
  // Linen curtain with irregular vertical folds, attached to the wall plane.
  polygon(c, [wall(10.5, 4.7), wall(11.15, 4.7), wall(11.05, 1.5), wall(10.45, 1.5)], '#ded9cc');
  for (let i = 0; i < 5; i++) line(c, wall(10.55 + i * .1, 4.6), wall(10.48 + i * .1, 1.55), i % 2 ? '#ece8de' : '#c9c3b6', 2);
}

function floor(c: Context) {
  box(c, 0, 0, 12, 12, -.22, .22, ['#c7a57d', '#a8825e', '#927052']);
  const timber = ['#c8a67e', '#c4a079', '#cfad86', '#caa67e', '#c5a27c', '#d1b08a'];
  for (let y = 0; y < 12; y += .55) {
    const d = Math.min(.55, 12 - y);
    plane(c, 0, y, 12, d, .003, timber[Math.round(y / .55) % timber.length]);
    line(c, iso(0, y), iso(12, y), 'rgba(102,74,47,.2)', .65);
    const offset = (Math.round(y / .55) % 3) * 1.3;
    for (let x = offset; x < 12; x += 3.9) line(c, iso(x, y), iso(x, y + d), 'rgba(96,67,42,.2)', .65);
    for (let g = 0; g < 4; g++) {
      const gy = y + .08 + g * .105;
      line(c, iso(.4 + g * .12, gy), iso(11.4 - g * .09, gy), 'rgba(107,73,43,.065)', .45);
    }
  }
  // Daylight lies on the floor in perspective, with a mullion gap.
  for (const y of [5.5, 8]) {
    polygon(c, [iso(.1, y), iso(.1, y + 2.05), iso(5.7, y + 3), iso(5.7, y + .95)], 'rgba(255,246,214,.23)');
  }
  plane(c, .8, 6.3, 4.7, 4.8, .018, '#aaa997');
  plane(c, .93, 6.43, 4.44, 4.54, .022, '#c4c0aa');
  for (let y = 6.5; y < 10.9; y += .11) line(c, iso(1, y, .023), iso(5.3, y, .023), 'rgba(247,240,214,.23)', .65);
  for (let x = 1; x < 5.4; x += .13) {
    line(c, iso(x, 6.2), iso(x, 6.38), '#d1cbb5', .7);
    line(c, iso(x, 10.98), iso(x, 11.17), '#d1cbb5', .7);
  }
}

export function drawRoom(c: Context) {
  c.fillStyle = '#f0eee7'; c.fillRect(0, 0, 1000, 760);
  ellipse(c, 503, 534, 396, 162, 'rgba(66,55,42,.035)');
  floor(c);
  polygon(c, [iso(0, 0), iso(0, 12), iso(0, 12, 5), iso(0, 0, 5)], '#e8e4d8');
  polygon(c, [iso(0, 0), iso(12, 0), iso(12, 0, 5), iso(0, 0, 5)], '#b7c2b2');
  // Wall caps and skirting give the cutaway actual thickness.
  polygon(c, [iso(0, 0, 5), iso(0, 12, 5), iso(-.14, 12, 5), iso(-.14, -.14, 5)], '#faf8ef');
  polygon(c, [iso(0, 0, 5), iso(12, 0, 5), iso(12, -.14, 5), iso(-.14, -.14, 5)], '#d5ddcf');
  line(c, iso(0, 0, .15), iso(0, 12, .15), '#cfc9ba', 5);
  line(c, iso(0, 0, .15), iso(12, 0, .15), '#8e9a87', 5);
  line(c, iso(0, 0, .26), iso(0, 12, .26), '#f4f0e5', 1);
  windowWall(c);
  // Framed architectural print, mounted on the sage wall.
  polygon(c, [iso(9.2, 0, 2.9), iso(10.8, 0, 2.9), iso(10.8, 0, 4.3), iso(9.2, 0, 4.3)], '#81745b');
  polygon(c, [iso(9.3, -.005, 3), iso(10.7, -.005, 3), iso(10.7, -.005, 4.2), iso(9.3, -.005, 4.2)], '#eeeadf');
  polygon(c, [iso(9.5, -.01, 3.1), iso(10.5, -.01, 3.1), iso(10, -.01, 3.9)], '#a8b29c');
  line(c, iso(9.5, -.02, 3.1), iso(10.5, -.02, 3.8), '#bf9e75', 2);
}
