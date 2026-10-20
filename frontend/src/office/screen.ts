import { iso, type Context } from './geometry';

export function drawDeskScreen(c: Context, screen?: { title: string; lines: string[] }) {
  const [x, y] = iso(6.14, 1.835, 3.85);
  c.save();
  c.transform(1, 18 / 34, 0, 1, x, y);
  c.beginPath(); c.rect(0, 0, 79.2, 39.7); c.clip();
  c.fillStyle = '#172c30'; c.fillRect(0, 0, 79.2, 39.7);
  c.fillStyle = '#b5d6b1'; c.font = 'bold 5px sans-serif';
  c.fillText((screen?.title || 'No active task').slice(0, 26), 4, 9, 72);
  c.fillStyle = '#e3e9df'; c.font = '4.5px sans-serif';
  const lines = screen?.lines.length ? screen.lines : ['Workspace is idle', 'Open desk for saved work'];
  lines.slice(0, 3).forEach((line, i) => c.fillText(line.slice(0, 30), 4, 18 + i * 7, 72));
  c.restore();
}
