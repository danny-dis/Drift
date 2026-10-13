import { ellipse, iso, line, rounded, shadow, type Context } from './geometry';

export interface OfficeStatus {
  position: { x: number; y: number };
  state: string;
  alert: boolean;
  activity: { type: string; detail: string };
  conversing: boolean;
  showCharacter?: boolean;
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

export function drawCharacter(c: Context, status: OfficeStatus, position: { x: number; y: number }, time: number) {
  if (status.showCharacter === false) return;
  const state = mood(status);
  const breath = state === 'sleep' ? Math.sin(time * .0009) * .7 : Math.sin(time * .0014) * .6;
  const [x, ground] = iso(position.x, position.y);
  const y = ground - 16 + breath;
  shadow(c, position.x, position.y, 20, 7);
  // A softly shaded crab keeps Drift's identity without the old pixel sprite.
  for (const sign of [-1, 1]) {
    for (let i = 0; i < 3; i++) {
      line(c, [x + sign * 11, y + 4 + i * 2], [x + sign * (22 - i), y + 9 + i * 2], '#a7654c', 2);
      line(c, [x + sign * (22 - i), y + 9 + i * 2], [x + sign * (25 - i), y + 5 + i * 4], '#c08466', 2);
    }
    line(c, [x + sign * 13, y + 1], [x + sign * 25, y - 4], '#b77458', 3);
    ellipse(c, x + sign * 27, y - 7, 7, 6, '#ce9575', sign * -.5);
    line(c, [x + sign * 26, y - 13], [x + sign * 29, y - 7], '#f0eee7', 2);
  }
  ellipse(c, x, y + 3, 19, 12, '#b87356');
  ellipse(c, x - 1, y, 18, 11, '#d79d7d');
  ellipse(c, x - 4, y - 4, 11, 4.5, 'rgba(249,217,180,.36)', -.16);
  for (const sign of [-1, 1]) {
    line(c, [x + sign * 8, y - 7], [x + sign * 9, y - 17], '#bd805f', 3);
    ellipse(c, x + sign * 9, y - 17, 4.2, 4.5, '#f0e1c9');
    if (state === 'sleep') line(c, [x + sign * 9 - 2, y - 17], [x + sign * 9 + 2, y - 17], '#3d4138', 1.5);
    else { ellipse(c, x + sign * 9 + (state === 'research' ? 1 : 0), y - 17, 2, 2.5, '#364439'); ellipse(c, x + sign * 9 - .6, y - 18, .65, .8, '#fff8e8'); }
  }
  c.beginPath(); c.arc(x, y + 2, 4, .15, Math.PI - .15); c.strokeStyle = '#935e48'; c.lineWidth = 1; c.stroke();
  if (state !== 'idle' || status.conversing) {
    rounded(c, x + 16, y - 48, 31, 22, 8, '#faf7eb');
    c.strokeStyle = '#b9bda9'; c.lineWidth = .7; c.stroke();
    c.fillStyle = state === 'blocked' ? '#945e44' : '#586b58';
    c.font = '600 13px system-ui'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(status.conversing ? '···' : state === 'sleep' ? 'z' : state === 'blocked' ? '!' : state === 'research' ? '⌕' : '···', x + 31, y - 37);
  }
}
