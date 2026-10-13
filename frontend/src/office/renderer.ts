import { WIDTH, HEIGHT, type Context } from './geometry';
import { drawRoom } from './room';
import { furniture } from './furniture';
import { clampPosition, drawCharacter, type OfficeStatus } from './character';

interface Layer { image: HTMLCanvasElement; x: number; y: number; width: number; height: number; depth: number }
function makeCanvas(width: number, height: number) {
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height; return canvas;
}
function cacheObject(draw: (c: Context) => void, depth: number, scale: number): Layer {
  const probe = makeCanvas(WIDTH, HEIGHT);
  const c = probe.getContext('2d')!; draw(c);
  const pixels = c.getImageData(0, 0, WIDTH, HEIGHT).data;
  let left = WIDTH, top = HEIGHT, right = 0, bottom = 0;
  for (let y = 0; y < HEIGHT; y++) for (let x = 0; x < WIDTH; x++) {
    if (pixels[(y * WIDTH + x) * 4 + 3]) { left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y); }
  }
  const width = right - left + 3, height = bottom - top + 3;
  const image = makeCanvas(Math.ceil(width * scale), Math.ceil(height * scale));
  const ctx = image.getContext('2d')!;
  ctx.scale(scale, scale); ctx.translate(1 - left, 1 - top); draw(ctx);
  probe.width = probe.height = 0;
  return { image, x: left - 1, y: top - 1, width: image.width / scale, height: image.height / scale, depth };
}

export function createOfficeRenderer(canvas: HTMLCanvasElement, initial: OfficeStatus, animation: boolean) {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas 2D is unavailable');
  let status = initial, animate = animation, disposed = false;
  let position = clampPosition(initial.position);
  let background: HTMLCanvasElement | null = null, layers: Layer[] = [], scale = 0;
  let frame = 0, previous = 0, visible = true;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const canAnimate = () => animate && !media.matches && !document.hidden && visible && !disposed;

  function rebuild() {
    const width = Math.max(1, Math.min(1200, canvas.getBoundingClientRect().width || WIDTH));
    const nextScale = width / WIDTH * Math.min(2, window.devicePixelRatio || 1);
    if (Math.abs(nextScale - scale) < .005 && background) return;
    background && (background.width = background.height = 0);
    layers.forEach(l => { l.image.width = l.image.height = 0; });
    scale = nextScale;
    canvas.width = Math.round(WIDTH * scale); canvas.height = Math.round(HEIGHT * scale);
    background = makeCanvas(canvas.width, canvas.height);
    const bg = background.getContext('2d')!; bg.scale(scale, scale); drawRoom(bg);
    layers = furniture.map(obj => cacheObject(obj.draw, obj.depth, scale)).sort((a, b) => a.depth - b.depth);
  }
  function paint(time = 0) {
    if (disposed || !background) return;
    const target = clampPosition(status.position);
    const moving = canAnimate();
    const delta = Math.min(50, previous ? time - previous : 16); previous = time;
    const ease = moving ? 1 - Math.exp(-delta / 120) : 1;
    position.x += (target.x - position.x) * ease; position.y += (target.y - position.y) * ease;
    ctx!.setTransform(1, 0, 0, 1, 0, 0); ctx!.clearRect(0, 0, canvas.width, canvas.height); ctx!.drawImage(background, 0, 0);
    ctx!.setTransform(scale, 0, 0, scale, 0, 0);
    const depth = position.x + position.y;
    let drawn = false;
    for (const layer of layers) {
      if (!drawn && layer.depth > depth) { drawCharacter(ctx!, status, position, moving ? time : 0); drawn = true; }
      ctx!.drawImage(layer.image, layer.x, layer.y, layer.width, layer.height);
    }
    if (!drawn) drawCharacter(ctx!, status, position, moving ? time : 0);
  }
  function tick(time: number) { frame = 0; paint(time); if (canAnimate()) frame = requestAnimationFrame(tick); }
  function refresh() {
    cancelAnimationFrame(frame); frame = 0; previous = 0;
    if (!document.hidden && visible) { paint(); if (canAnimate()) frame = requestAnimationFrame(tick); }
  }
  const observer = new ResizeObserver(() => { rebuild(); refresh(); }); observer.observe(canvas);
  const intersection = typeof IntersectionObserver !== 'undefined' ? new IntersectionObserver(entries => { visible = entries[0].isIntersecting; refresh(); }) : null;
  intersection?.observe(canvas);
  const resize = () => { rebuild(); refresh(); };
  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', refresh);
  media.addEventListener('change', refresh);
  rebuild(); refresh();
  return {
    update(next: OfficeStatus, enabled: boolean) { status = next; animate = enabled; refresh(); },
    dispose() {
      disposed = true; cancelAnimationFrame(frame); observer.disconnect(); intersection?.disconnect();
      window.removeEventListener('resize', resize); document.removeEventListener('visibilitychange', refresh); media.removeEventListener('change', refresh);
      if (background) background.width = background.height = 0;
      layers.forEach(layer => { layer.image.width = layer.image.height = 0; }); layers = [];
    },
  };
}
