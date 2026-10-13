import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { createOfficeRenderer } from "./renderer";
import type { OfficeStatus } from "./character";
import "./office.css";

export interface OfficeCanvasHandle { snapshot: () => string }
type Props = { status: OfficeStatus; animated?: boolean; label?: string };

const OfficeCanvas = forwardRef<OfficeCanvasHandle, Props>(
  ({ status, animated = false, label = "Drift's isometric office" }, ref) => {
    const canvas = useRef<HTMLCanvasElement>(null);
    const renderer = useRef<ReturnType<typeof createOfficeRenderer> | null>(null);
    const current = useRef({ status, animated });
    current.current = { status, animated };
    const [error, setError] = useState("");

    useImperativeHandle(ref, () => ({
      snapshot: () => {
        try { return canvas.current?.toDataURL("image/png") || ""; }
        catch { return ""; }
      },
    }), []);

    useEffect(() => {
      if (!canvas.current) return;
      try {
        renderer.current = createOfficeRenderer(canvas.current, current.current.status, current.current.animated);
        setError("");
      } catch { setError("The office graphics are unavailable on this browser. Thought capture still works."); }
      return () => { renderer.current?.dispose(); renderer.current = null; };
    }, []);

    useEffect(() => { renderer.current?.update(status, animated); }, [status, animated]);

    return <div className="office-canvas-wrap">
      <canvas ref={canvas} width={1000} height={760} className="office-canvas" role="img" aria-label={label}>
        A furnished isometric studio office with daylight, shelving, plants and Drift's companion.
      </canvas>
      {error && <p className="office-error" role="status">{error}</p>}
    </div>;
  },
);
OfficeCanvas.displayName = "OfficeCanvas";
export default OfficeCanvas;
