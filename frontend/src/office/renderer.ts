import { WIDTH, HEIGHT, iso, type Context } from './geometry';
import { drawRoom } from './room';
import { furniture } from './furniture';
import { drawCharacter, type OfficeStatus } from './character';
import { officePosition, officeRoute, walkStep, type OfficeActivity, type OfficePoint } from './motion';
import { drawDeskScreen } from './screen';

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

export function createOfficeRenderer(canvas: HTMLCanvasElement, initial: OfficeStatus & { closeUp?: boolean }, animation: boolean) {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas 2D is unavailable');
  let status = initial, animate = animation, disposed = false;
  const activity = () => (['browsing','writing','reading','thinking','waiting'].includes(status.activity.type) ? status.activity.type : 'idle') as OfficeActivity;
  let goal = activity(), position = officePosition(goal), route: OfficePoint[] = [], facing = 1;
  let background: HTMLCanvasElement | null = null, layers: Layer[] = [], scale = 0;
  let frame = 0, previous = 0, motionTime = 0, visible = true, cachedZoom = 0;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const canAnimate = () => animate && status.showCharacter !== false && !media.matches && !document.hidden && visible && !disposed;

  function rebuild() {
    const width = Math.max(1, Math.min(1200, canvas.getBoundingClientRect().width || WIDTH));
    const nextScale = width / WIDTH * Math.min(2, window.devicePixelRatio || 1);
    const zoom = status.closeUp ? 2.2 : 1;
    if (Math.abs(nextScale - scale) < .005 && cachedZoom === zoom && background) return;
    background && (background.width = background.height = 0);
    layers.forEach(l => { l.image.width = l.image.height = 0; });
    scale = nextScale; cachedZoom = zoom;
    canvas.width = Math.round(WIDTH * scale); canvas.height = Math.round(HEIGHT * scale);
    const cacheScale = Math.min(2, scale * zoom);
    background = makeCanvas(Math.ceil(WIDTH * cacheScale), Math.ceil(HEIGHT * cacheScale));
    const bg = background.getContext('2d')!; bg.scale(cacheScale, cacheScale); drawRoom(bg);
    layers = furniture.map(obj => cacheObject(obj.draw, obj.depth, cacheScale)).sort((a, b) => a.depth - b.depth);
  }
  function paint(time = 0) {
    if (disposed || !background) return;
    const moving = canAnimate();
    const delta = time ? Math.min(50, previous ? time - previous : 16) : 0; previous = time;
    if (moving) {
      motionTime += delta;
      if (route.length) {
        const next = walkStep(position, route[0], delta);
        if (next.x !== position.x || next.y !== position.y) facing = Math.atan2(next.y-position.y,next.x-position.x);
        position = next;
        if (Math.hypot(position.x-route[0].x,position.y-route[0].y) < .001) route.shift();
      }
    }
    ctx!.setTransform(1, 0, 0, 1, 0, 0); ctx!.clearRect(0, 0, canvas.width, canvas.height);
    const zoom = status.closeUp ? 2.2 : 1, center = iso(position.x, position.y);
    const desk = !route.length && ['browsing','writing'].includes(goal);
    const cameraX = status.closeUp ? Math.max(0, Math.min(WIDTH-WIDTH/zoom,(desk ? 650 : center[0])-WIDTH/zoom/2)) : 0;
    const cameraY = status.closeUp ? Math.max(0, Math.min(HEIGHT-HEIGHT/zoom,(desk ? 335 : center[1]-65)-HEIGHT/zoom/2)) : 0;
    ctx!.setTransform(scale*zoom, 0, 0, scale*zoom, -cameraX*scale*zoom, -cameraY*scale*zoom);
    ctx!.drawImage(background, 0, 0, WIDTH, HEIGHT);
    const depth = position.x + position.y + (!route.length && ['idle','waiting'].includes(goal) ? .7 : 0);
    const pose = { walking: route.length > 0, facing };
    let drawn = false;
    for (const layer of layers) {
      if (!drawn && layer.depth > depth) { drawCharacter(ctx!, status, position, motionTime, pose); drawn = true; }
      ctx!.drawImage(layer.image, layer.x, layer.y, layer.width, layer.height);
      if (layer.depth === 9.5) drawDeskScreen(ctx!, status.screen);
    }
    if (!drawn) drawCharacter(ctx!, status, position, motionTime, pose);
  }
  function tick(time: number) {
    frame = 0;
    if (!previous || time - previous >= 1000 / 30) paint(time);
    if (canAnimate()) frame = requestAnimationFrame(tick);
  }
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
    update(next: OfficeStatus & { closeUp?: boolean }, enabled: boolean) {
      status = next; animate = enabled;
      if (activity() !== goal) {
        goal = activity();
        if (!enabled || media.matches) { position = officePosition(goal); route = []; }
        else route = officeRoute(position, goal);
      }
      rebuild(); refresh();
    },
    dispose() {
      disposed = true; cancelAnimationFrame(frame); observer.disconnect(); intersection?.disconnect();
      window.removeEventListener('resize', resize); document.removeEventListener('visibilitychange', refresh); media.removeEventListener('change', refresh);
      if (background) background.width = background.height = 0;
      layers.forEach(layer => { layer.image.width = layer.image.height = 0; }); layers = [];
    },
  };
}
