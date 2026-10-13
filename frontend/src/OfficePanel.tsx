import { useMemo, useState } from "react";
import OfficeCanvas from "./office/OfficeCanvas";
import type { OfficeStatus } from "./office/character";
import "./office/office.css";

type Props = { state: string; name: string; activity?: string; connected: boolean };

export default function OfficePanel({ state, name, activity = "", connected }: Props) {
  const [animated, setAnimated] = useState(false);
  const status = useMemo<OfficeStatus>(() => ({
    position: { x: 5.4, y: 5.8 }, state, alert: /blocked|error/.test(state),
    activity: { type: activity, detail: "" }, conversing: false, showCharacter: connected,
  }), [state, activity, connected]);
  const caption = connected ? `${name || "Drift"} · ${state || "idle"}` : "Backend status unavailable";

  return <section className="office-panel" aria-labelledby="office-title">
    <header className="office-heading">
      <div><p className="office-eyebrow">THE WORKSPACE</p><h2 id="office-title">A quiet place to think</h2></div>
      <label className="office-motion"><input type="checkbox" checked={animated} onChange={event => setAnimated(event.target.checked)} />Gentle animation</label>
    </header>
    <OfficeCanvas status={status} animated={animated} label={`Furnished studio office. ${caption}. Character position is illustrative.`} />
    <div className="office-caption">
      <p role="status"><span className={`office-status-dot${connected ? " office-connected" : ""}`} aria-hidden="true" />{caption}</p>
      <span>Daylight studio · original 2D artwork</span>
    </div>
    <p className="office-note">Activity reflects the latest backend status; the scene and character position are illustrative. Animation is optional and respects reduced-motion settings.</p>
  </section>;
}
