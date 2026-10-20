import { ellipse, iso, line, polygon, rounded, type Context, type Point } from './geometry';
import { KEYBOARD_HANDS, DESK_MOUSE } from './layout';

export interface OfficeStatus {
  position: { x: number; y: number };
  state: string;
  alert: boolean;
  activity: { type: string; detail: string };
  conversing: boolean;
  showCharacter?: boolean;
  screen?: { title: string; lines: string[] };
}
export function mood(status: OfficeStatus): 'idle' | 'thinking' | 'research' | 'sleep' | 'blocked' {
  const s = status.state.toLowerCase();
  if (status.alert || /blocked|error|approval/.test(s)) return 'blocked';
  if (/sleep|rest|dormant/.test(s)) return 'sleep';
  if (/research|search|reading/.test(s) || /search|reading/.test(status.activity.type)) return 'research';
  if (/think|reflect|plan|working|active/.test(s)) return 'thinking';
  return 'idle';
}
export const clampPosition = (p: { x: number; y: number }) => ({
  x: Math.max(.55, Math.min(11.45, (Number.isFinite(p.x) ? p.x : 7) + .5)),
  y: Math.max(.55, Math.min(11.45, (Number.isFinite(p.y) ? p.y : 5) + .5)),
});

const fur = ['#fffdf2', '#ecebdf', '#a9b3aa'] as const;
const charcoal = ['#69736f', '#303c3a', '#111d1e'] as const;

function orb(c: Context, x: number, y: number, rx: number, ry: number,
  colors: readonly [string, string, string], rotation = 0) {
  c.save(); c.translate(x, y); c.rotate(rotation); c.scale(rx, ry);
  const light = c.createRadialGradient(-.36, -.44, .04, .12, .2, 1.15);
  light.addColorStop(0, colors[0]); light.addColorStop(.48, colors[1]); light.addColorStop(1, colors[2]);
  c.beginPath(); c.arc(0, 0, 1, 0, Math.PI * 2); c.fillStyle = light; c.fill(); c.restore();
}

function arm(c: Context, shoulder: Point, elbow: Point, paw: Point) {
  c.beginPath(); c.moveTo(...shoulder); c.quadraticCurveTo(...elbow, ...paw);
  c.strokeStyle = '#172526'; c.lineWidth = 12; c.lineCap = 'round'; c.stroke();
  c.beginPath(); c.moveTo(shoulder[0] - 2, shoulder[1] - 2);
  c.quadraticCurveTo(elbow[0] - 2, elbow[1] - 2, paw[0] - 1, paw[1] - 2);
  c.strokeStyle = '#4a5853'; c.lineWidth = 5; c.stroke();
  orb(c, ...paw, 6.5, 7, charcoal, -.2);
}

function book(c: Context, y: number) {
  polygon(c, [[-18, y - 7], [0, y - 3], [18, y - 8], [16, y + 9], [0, y + 13], [-17, y + 9]], '#546e63');
  polygon(c, [[-16, y - 6], [0, y - 2], [0, y + 10], [-15, y + 7]], '#efe5c9');
  polygon(c, [[0, y - 2], [16, y - 7], [14, y + 7], [0, y + 10]], '#fff6de');
  line(c, [0, y - 2], [0, y + 10], '#aeab91', .8);
  for (let i = 0; i < 3; i++) {
    line(c, [-12, y - 2 + i * 3], [-3, y + i * 3], '#b8b69e', .6);
    line(c, [3, y + i * 3], [12, y - 3 + i * 3], '#b8b69e', .6);
  }
}

function head(c: Context, y: number, look: number, sleepy: boolean, time: number, speaking: boolean, back = false) {
  c.save(); c.translate(look * 2, y); c.rotate(look * .035);
  orb(c, -17, -17, 9, 10, charcoal, -.3);
  orb(c, 18, -18, 9, 10, charcoal, .3);
  ellipse(c, -18, -17, 4.5, 5.5, '#40504a');
  ellipse(c, 18, -18, 4.5, 5.5, '#374840');
  ellipse(c, 1, 7, 23, 17, 'rgba(14,28,25,.16)');
  orb(c, 0, 0, 26, 24, fur, -.05);
  // Deterministic guard hairs soften the silhouette at desk zoom.
  for (let i = 0; i < 9; i++) {
    const x = -15 + i * 3.6;
    const top = -Math.sqrt(Math.max(0, 1 - (x / 26) ** 2)) * 24;
    line(c, [x, top + 2], [x - .8, top - .6], 'rgba(255,253,242,.6)', .7);
  }
  if (back) { c.restore(); return; }
  const face = look * 5;
  const blink = sleepy || Math.sin(time * .00031) > .996;
  for (const side of [-1, 1]) {
    const x = side * 10 + face;
    orb(c, x, 1, side === Math.sign(look) ? 8 : 7, 10.5, charcoal, side * -.35);
    if (blink) {
      c.beginPath(); c.ellipse(x + look, 1, 3.3, 1.7, 0, .1, Math.PI - .1);
      c.strokeStyle = '#c0c8bb'; c.lineWidth = 1.2; c.stroke();
    } else {
      orb(c, x + look, .5, 3.4, 4, ['#acb8a3', '#596b5b', '#263631']);
      ellipse(c, x + look + .3, .8, 2.1, 3, '#111c1b');
      ellipse(c, x + look - .8, -.8, 1.25, 1.4, '#fffef4');
      ellipse(c, x + look + 1, 2.1, .5, .6, '#c4d7cb');
    }
  }
  orb(c, face, 11, 13, 9, ['#fffdf1', '#e7e6d7', '#b5bcb0']);
  orb(c, face, 7.5, 5.2, 3.6, charcoal);
  ellipse(c, face - 1.2, 6.4, 1.8, .7, 'rgba(224,235,220,.55)', -.1);
  line(c, [face, 10], [face, 13.5], '#4c5b50', .9);
  c.beginPath(); c.moveTo(face - 4, 13); c.quadraticCurveTo(face, 17, face + 4, 13);
  c.strokeStyle = '#657060'; c.lineWidth = .9; c.stroke();
  if (speaking) ellipse(c, face, 15, 2.3, 1 + Math.abs(Math.sin(time * .008)) * 1.6, '#465449');
  for (const side of [-1, 1]) for (let i = 0; i < 2; i++) {
    ellipse(c, face + side * (7 + i * 2), 11 + i * 2, .5, .5, '#b5bbac');
  }
  c.restore();
}

export function drawCharacter(c: Context, status: OfficeStatus, position: { x: number; y: number }, time: number,
  motion?: { walking: boolean; facing?: number }) {
  if (status.showCharacter === false) return;
  const walking = motion?.walking === true;
  const activity = status.activity.type;
  const desk = !walking && (activity === 'writing' || activity === 'browsing');
  const resting = !walking && (activity === 'idle' || activity === 'waiting');
  const seated = desk || resting;
  const reading = !walking && activity === 'reading';
  const thinking = !walking && activity === 'thinking';
  const state = mood(status);
  const clock = Number.isFinite(time) ? time : 0;
  const gait = walking ? Math.sin(clock * .009) : 0;
  const breath = Math.sin(clock * .0018) * .55;
  const z = resting ? 1 : desk ? .8 : 0;
  const [x, ground] = iso(position.x, position.y, z);
  const facing = motion?.facing;
  const look = walking && facing !== undefined && Number.isFinite(facing)
    ? Math.max(-1, Math.min(1, (Math.cos(facing) - Math.sin(facing)) / Math.SQRT2))
    : desk ? .85 : thinking ? -.7 : reading ? -.25 : .12;

  c.save(); c.translate(x, ground);
  // Seat contact belongs on its elevated cushion, not the floor or desktop.
  const shade = c.createRadialGradient(0, 1, 2, 0, 1, seated ? 27 : 24);
  shade.addColorStop(0, 'rgba(24,35,29,.25)'); shade.addColorStop(1, 'rgba(24,35,29,0)');
  c.save(); c.scale(1, .32); c.fillStyle = shade;
  c.beginPath(); c.arc(0, 1, seated ? 27 : 24, 0, Math.PI * 2); c.fill(); c.restore();
  c.translate(0, breath - (walking ? Math.abs(gait) * 1.6 : 0));
  const hips = seated ? -12 : -27;
  const neck = desk ? -57 : seated ? -38 : -51;
  const headY = desk ? -77 : seated ? -55 : -66;

  orb(c, -17, hips + 4, 10, seated ? 12 : 15, charcoal, -.25 - gait * .18);
  orb(c, 17, hips + 4, 10, seated ? 12 : 15, charcoal, .25 + gait * .18);
  if (!seated) {
    orb(c, -12 - gait * 2.5, -7 - Math.max(0, gait) * 4, 10, 9, charcoal, -.12);
    orb(c, 12 + gait * 2.5, -7 - Math.max(0, -gait) * 4, 10, 9, charcoal, .12);
  }
  orb(c, 0, hips - (desk ? 20 : 10), 23, desk ? 34 : seated ? 24 : 27, fur, look * -.04);
  orb(c, look * 2, neck + 7, 23, 12, charcoal, -.08);
  orb(c, -1, hips - 7, 18, seated ? 19 : 22, fur, -.12);
  ellipse(c, -8, hips - 12, 6, 11, 'rgba(255,253,240,.28)', -.3);
  for (let i = 0; i < 5; i++) {
    line(c, [-13 + i * 6, hips + 9], [-14 + i * 6, hips + 12], 'rgba(155,168,152,.23)', .6);
  }
  if (seated) {
    orb(c, -17, 1, 11, 8, charcoal, -.22);
    orb(c, 17, 1, 11, 8, charcoal, .22);
    for (const side of [-1, 1]) {
      ellipse(c, side * 18, 2, 5, 3.5, '#536058', side * .15);
      for (let i = 0; i < 2; i++) line(c, [side * 18 - 2 + i * 3, -2], [side * 18 - 2 + i * 3, 0], '#849083', .7);
    }
  }

  if (!desk) head(c, headY + breath * .3, look, state === 'sleep' && !walking, clock, status.conversing);
  const shoulders: [Point, Point] = [[-18, neck + 6], [18, neck + 6]];
  if (reading) {
    arm(c, shoulders[0], [-25, -29], [-17, -28]);
    arm(c, shoulders[1], [25, -29], [17, -28]);
    book(c, -30);
    orb(c, -17, -25, 5, 6, charcoal, -.3);
    orb(c, 17, -26, 5, 6, charcoal, .3);
  } else if (desk) {
    const typing = activity === 'writing';
    const tap = typing ? Math.sin(clock * .018) * 1.8 : Math.sin(clock * .002) * .8;
    const left = iso(KEYBOARD_HANDS[0].x, KEYBOARD_HANDS[0].y, KEYBOARD_HANDS[0].z);
    const rightTarget = typing ? KEYBOARD_HANDS[1] : DESK_MOUSE;
    const right = iso(rightTarget.x, rightTarget.y, rightTarget.z);
    arm(c, shoulders[0], [-12, -65], [left[0]-x, left[1]-ground-breath+tap]);
    arm(c, shoulders[1], [32, -55], [right[0]-x, right[1]-ground-breath-tap]);
  } else if (thinking) {
    arm(c, shoulders[0], [-25, -28], [-15, -18]);
    arm(c, shoulders[1], [30, -40], [14, headY + 17]);
  } else {
    for (let i = 0; i < 2; i++) {
      const side = i ? 1 : -1;
      // The leading paw reaches towards the shelf while the reader approaches.
      const reach = walking && activity === 'reading' && side === -1;
      arm(c, shoulders[i], [side * 27, neck + 23],
        [side * (resting ? 16 : 24) + gait * side * 3, reach ? neck - 3 : hips + (walking ? gait * side * 7 : 1)]);
    }
  }
  if (desk) { c.save(); c.translate(-10, 0); head(c, headY, look, false, clock, false, true); c.restore(); }
  if (status.alert || state === 'blocked' || status.conversing) {
    rounded(c, 29, headY - 31, 22, 20, 7, '#fbf4df');
    c.strokeStyle = '#b5bda8'; c.lineWidth = .7; c.stroke();
    c.fillStyle = status.alert || state === 'blocked' ? '#975c3c' : '#526853';
    c.font = '600 12px system-ui'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(status.conversing ? '···' : '!', 40, headY - 21);
  }
  c.restore();
}
