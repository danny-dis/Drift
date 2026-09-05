/**
 * Pixel-art game world rendered on HTML5 Canvas.
 * Uses pre-rendered room background + character sprite sheet.
 */

import { useRef, useEffect, useImperativeHandle, forwardRef } from "react";
import { COLS, ROWS, TILE, CHAR_SIZE, FRAMES, WALK_SEQ, IDLE_FRAME } from "./sprites";

const W = COLS * TILE; // 384
const H = ROWS * TILE; // 384
const DISPLAY_SIZE = 48; // match sprite native size

interface Activity {
  type: string;
  detail: string;
}

interface Props {
  position: { x: number; y: number };
  state: string;
  alert: boolean;
  activity: Activity;
  conversing: boolean;
}

export interface GameWorldHandle {
  snapshot: () => string;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.src = src;
  });
}

// --- Activity drawing helpers ---

function drawTerminal(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Dark terminal window
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(x - 12, y - 8, 24, 16);
  ctx.strokeStyle = "#475569";
  ctx.lineWidth = 1;
  ctx.strokeRect(x - 12, y - 8, 24, 16);
  // Green prompt
  ctx.fillStyle = "#22c55e";
  ctx.font = "bold 8px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const blink = Math.floor(Date.now() / 500) % 2 === 0;
  ctx.fillText(blink ? ">_" : "> ", x, y);
}

function drawPython(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Blue-yellow python badge
  ctx.fillStyle = "#1e3a5f";
  ctx.fillRect(x - 12, y - 8, 24, 16);
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 1;
  ctx.strokeRect(x - 12, y - 8, 24, 16);
  ctx.fillStyle = "#fbbf24";
  ctx.font = "bold 8px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("py", x, y);
}

function drawSearching(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const t = Date.now() / 400;
  const wobble = Math.sin(t) * 2;
  // Magnifying glass — circle + handle
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(x + wobble, y - 2, 6, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + 4 + wobble, y + 2);
  ctx.lineTo(x + 8 + wobble, y + 6);
  ctx.stroke();
}

function drawWriting(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Little paper
  ctx.fillStyle = "#fefce8";
  ctx.fillRect(x - 6, y - 7, 12, 14);
  ctx.strokeStyle = "#d4d4d8";
  ctx.lineWidth = 0.5;
  ctx.strokeRect(x - 6, y - 7, 12, 14);
  // Lines on paper
  ctx.fillStyle = "#94a3b8";
  ctx.fillRect(x - 4, y - 4, 8, 1);
  ctx.fillRect(x - 4, y - 1, 8, 1);
  ctx.fillRect(x - 4, y + 2, 5, 1);
  // Animated pencil
  const bob = Math.sin(Date.now() / 200) * 1.5;
  ctx.fillStyle = "#f59e0b";
  ctx.fillRect(x + 4, y - 2 + bob, 2, 8);
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(x + 4, y + 5 + bob, 2, 2); // tip
}

function drawReading(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Open book
  ctx.fillStyle = "#dbeafe";
  ctx.fillRect(x - 8, y - 5, 7, 10);
  ctx.fillRect(x + 1, y - 5, 7, 10);
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 0.5;
  ctx.strokeRect(x - 8, y - 5, 7, 10);
  ctx.strokeRect(x + 1, y - 5, 7, 10);
  // Spine
  ctx.fillStyle = "#3b82f6";
  ctx.fillRect(x - 1, y - 6, 2, 12);
  // Lines
  ctx.fillStyle = "#93c5fd";
  ctx.fillRect(x - 6, y - 2, 4, 1);
  ctx.fillRect(x - 6, y + 1, 4, 1);
  ctx.fillRect(x + 3, y - 2, 4, 1);
  ctx.fillRect(x + 3, y + 1, 4, 1);
}

const GameWorld = forwardRef<GameWorldHandle, Props>(
  ({ position, state, alert, activity, conversing }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const posRef = useRef({ x: position.x, y: position.y });
    const targetRef = useRef({ x: position.x, y: position.y });
    const dirRef = useRef<string>("down");
    const stateRef = useRef(state);
    const alertRef = useRef(alert);
    const activityRef = useRef(activity);
    const conversingRef = useRef(conversing);
    const walkIndexRef = useRef(0);
    const frameCountRef = useRef(0);
    const roomImgRef = useRef<HTMLImageElement | null>(null);
    const charImgRef = useRef<HTMLImageElement | null>(null);

    useImperativeHandle(ref, () => ({
      snapshot: () => canvasRef.current?.toDataURL() || "",
    }));

    useEffect(() => {
      targetRef.current = { x: position.x, y: position.y };
    }, [position.x, position.y]);

    useEffect(() => {
      stateRef.current = state;
    }, [state]);

    useEffect(() => {
      alertRef.current = alert;
    }, [alert]);

    useEffect(() => {
      activityRef.current = activity;
    }, [activity]);

    useEffect(() => {
      conversingRef.current = conversing;
    }, [conversing]);

    // Load images and start render loop
    useEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d")!;
      ctx.imageSmoothingEnabled = false;
      let animId: number;
      let running = true;

      (async () => {
        const [roomImg, charImg] = await Promise.all([
          loadImage("/room.png"),
          loadImage("/character.png"),
        ]);
        roomImgRef.current = roomImg;
        charImgRef.current = charImg;

        const render = () => {
          if (!running) return;
          const pos = posRef.current;
          const target = targetRef.current;
          const dx = target.x - pos.x;
          const dy = target.y - pos.y;
          const moving = Math.abs(dx) > 0.02 || Math.abs(dy) > 0.02;

          if (moving) {
            pos.x += dx * 0.1;
            pos.y += dy * 0.1;
            if (Math.abs(dx) > Math.abs(dy)) {
              dirRef.current = dx > 0 ? "right" : "left";
            } else {
              dirRef.current = dy > 0 ? "down" : "up";
            }
            frameCountRef.current++;
            if (frameCountRef.current % 8 === 0) {
              walkIndexRef.current =
                (walkIndexRef.current + 1) % WALK_SEQ.length;
            }
          } else {
            pos.x = target.x;
            pos.y = target.y;
            walkIndexRef.current = 0;
          }

          // Clear
          ctx.clearRect(0, 0, W, H);

          // Room background
          ctx.drawImage(roomImg, 0, 0, W, H);

          // Character sprite
          const dir = dirRef.current;
          const frames = FRAMES[dir] || FRAMES.down;
          const frameIdx = moving
            ? WALK_SEQ[walkIndexRef.current]
            : IDLE_FRAME;
          const frame = frames[frameIdx];

          const charX = pos.x * TILE + TILE / 2 - DISPLAY_SIZE / 2;
          const charY = pos.y * TILE + TILE - DISPLAY_SIZE;
          ctx.drawImage(
            charImg,
            frame.x,
            frame.y,
            CHAR_SIZE,
            CHAR_SIZE,
            charX,
            charY,
            DISPLAY_SIZE,
            DISPLAY_SIZE,
          );

          // State indicator (above crab)
          const curState = stateRef.current;
          const indicatorX = charX + DISPLAY_SIZE / 2;
          const indicatorY = charY - 8;

          if (curState === "thinking") {
            // Thought bubble
            ctx.fillStyle = "#fff";
            ctx.beginPath();
            ctx.arc(indicatorX, indicatorY - 6, 7, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = "#888";
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.fillStyle = "#666";
            ctx.font = "9px monospace";
            ctx.textAlign = "center";
            ctx.fillText("...", indicatorX, indicatorY - 3);
            // Small dots
            ctx.fillStyle = "#fff";
            ctx.beginPath();
            ctx.arc(indicatorX + 5, indicatorY + 3, 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(indicatorX + 3, indicatorY + 6, 1.5, 0, Math.PI * 2);
            ctx.fill();
          } else if (curState === "reflecting") {
            // Sparkle
            const t = Date.now() / 200;
            ctx.fillStyle = "#c084fc";
            for (let i = 0; i < 4; i++) {
              const angle = (Math.PI / 2) * i + t;
              const sx = indicatorX + Math.cos(angle) * 6;
              const sy = indicatorY - 6 + Math.sin(angle) * 6;
              ctx.beginPath();
              ctx.arc(sx, sy, 2, 0, Math.PI * 2);
              ctx.fill();
            }
            ctx.fillStyle = "#a855f7";
            ctx.beginPath();
            ctx.arc(indicatorX, indicatorY - 6, 3, 0, Math.PI * 2);
            ctx.fill();
          } else if (curState === "planning") {
            // Clipboard/checklist icon — green notepad with lines
            const padX = indicatorX - 5;
            const padY = indicatorY - 16;
            // Notepad background
            ctx.fillStyle = "#14b8a6";
            ctx.fillRect(padX, padY, 10, 12);
            ctx.fillStyle = "#0d9488";
            ctx.fillRect(padX + 1, padY - 2, 8, 3); // clip at top
            // Lines on notepad
            ctx.fillStyle = "#fff";
            ctx.fillRect(padX + 2, padY + 3, 6, 1);
            ctx.fillRect(padX + 2, padY + 6, 6, 1);
            ctx.fillRect(padX + 2, padY + 9, 4, 1);
          }

          // Conversation indicator — speech bubble when talking to user
          if (conversingRef.current) {
            const bx = indicatorX - 8;
            const by = indicatorY - 20;
            // Two overlapping rounded rects to form speech bubble
            ctx.fillStyle = "#ea580c";
            ctx.beginPath();
            ctx.roundRect(bx - 4, by - 4, 24, 14, 4);
            ctx.fill();
            // Small triangle tail
            ctx.beginPath();
            ctx.moveTo(bx + 2, by + 10);
            ctx.lineTo(bx + 6, by + 15);
            ctx.lineTo(bx + 10, by + 10);
            ctx.fill();
            // Dots inside bubble
            ctx.fillStyle = "#fff";
            ctx.beginPath();
            ctx.arc(bx + 4, by + 3, 2, 0, Math.PI * 2);
            ctx.arc(bx + 10, by + 3, 2, 0, Math.PI * 2);
            ctx.arc(bx + 16, by + 3, 2, 0, Math.PI * 2);
            ctx.fill();
          }

          // Activity indicator (to the right of crab)
          const act = activityRef.current;
          if (act.type !== "idle" && act.type !== "moving") {
            const actX = charX + DISPLAY_SIZE + 8;
            const actY = charY + DISPLAY_SIZE / 2;

            if (act.type === "shell") drawTerminal(ctx, actX, actY);
            else if (act.type === "python") drawPython(ctx, actX, actY);
            else if (act.type === "searching") drawSearching(ctx, actX, actY);
            else if (act.type === "writing") drawWriting(ctx, actX, actY);
            else if (act.type === "reading") drawReading(ctx, actX, actY);
            else if (act.type === "conversing") {
              // Small speech lines
              ctx.strokeStyle = "#ea580c";
              ctx.lineWidth = 2;
              for (let i = 0; i < 3; i++) {
                const ly = actY - 4 + i * 4;
                ctx.beginPath();
                ctx.moveTo(actX - 6, ly);
                ctx.lineTo(actX + 6 - i * 2, ly);
                ctx.stroke();
              }
            }
          }

          // Alert indicator — red ! bubble with gentle bounce
          if (alertRef.current) {
            const bounce = Math.sin(Date.now() / 300) * 3;
            const alertY = indicatorY - 14 + bounce;
            ctx.fillStyle = "#ef4444";
            ctx.beginPath();
            ctx.arc(indicatorX, alertY, 8, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = "#fff";
            ctx.font = "bold 11px monospace";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("!", indicatorX, alertY);
          }

          // Activity detail text (bottom of canvas)
          if (act.type !== "idle" && act.detail) {
            const label = act.detail.length > 40
              ? act.detail.slice(0, 40) + "..."
              : act.detail;
            ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
            ctx.fillRect(0, H - 20, W, 20);
            ctx.fillStyle = "#e2e8f0";
            ctx.font = "10px monospace";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(label, W / 2, H - 10);
          }

          animId = requestAnimationFrame(render);
        };

        animId = requestAnimationFrame(render);
      })();

      return () => {
        running = false;
        cancelAnimationFrame(animId);
      };
    }, []);

    return (
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        style={{
          width: "100%",
          maxWidth: W * 2,
          imageRendering: "pixelated",
          borderRadius: 8,
        }}
      />
    );
  },
);

export default GameWorld;
