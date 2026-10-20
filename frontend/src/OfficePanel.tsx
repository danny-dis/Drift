import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import OfficeCanvas from "./office/OfficeCanvas";
import { type OfficeStatus } from "./office/character";
import DeskView from "./office/DeskView";
import type { OfficeWork, WorkTask, WorkProject } from "./office/work-context";
import "./office/office.css";

type Props = { state: string; name: string; connected: boolean; work: OfficeWork; savedTask?: WorkTask; savedProject?: WorkProject; headers: () => Record<string,string>; onProject: (id: string) => void };
const ACTIONS = { idle: 'Relaxing on the couch', browsing: 'Browsing at the computer', writing: 'Writing at the computer', reading: 'Reading by the bookshelf', thinking: 'Thinking by the window', waiting: 'Waiting on the couch' };

export default function OfficePanel({ state, name, connected, work, savedTask, savedProject, headers, onProject }: Props) {
  const [animated, setAnimated] = useState(() => {
    try { return localStorage.getItem('drift-office-motion') !== 'off'; }
    catch { return true; }
  });
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [expanded, setExpanded] = useState(false);
  const [screenNote, setScreenNote] = useState("");
  const [closeUp, setCloseUp] = useState(false);
  const [preview, setPreview] = useState<{id: string; text: string} | null>(null);
  const reportReceived = useCallback((id: string, text: string) => setPreview({ id, text }), []);
  const deskTask = work.mode === 'idle' ? savedTask : work.task;
  const deskProject = work.mode === 'idle' ? savedProject : work.project;
  const screenTitle = deskProject ? `${work.mode === 'idle' ? 'Saved · ' : ''}${deskProject.name}` : work.mode === 'idle' ? 'Saved work · not running' : 'Current task';
  const screenText = preview?.id === deskTask?.id ? preview?.text : deskTask?.source_text || deskTask?.goal || '';
  const scene = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const motion = () => setReduced(media.matches);
    const fullscreen = () => setExpanded(document.fullscreenElement === scene.current);
    media.addEventListener('change', motion);
    document.addEventListener('fullscreenchange', fullscreen);
    return () => {
      media.removeEventListener('change', motion);
      document.removeEventListener('fullscreenchange', fullscreen);
    };
  }, []);
  const status = useMemo<OfficeStatus & {closeUp?: boolean}>(() => ({
    position: { x: 5.5, y: 5.1 }, state, alert: /blocked|error/.test(state),
    activity: { type: work.kind, detail: work.project?.name || '' }, conversing: false, showCharacter: connected,
    closeUp, screen: { title: screenTitle, lines: screenText ? screenText.split(/\n/).filter(Boolean).slice(0,3) : ['No active task', 'Workspace is idle'] },
  }), [state, work.kind, work.mode, work.project?.name, connected, closeUp, screenText, screenTitle]);
  const caption = connected ? `${name || "Drift"} · ${state || "idle"}` : "Waiting for the workspace to reconnect";
  const motionCaption = !connected ? "Waiting for connection" : reduced ? "Movement paused by your reduced-motion setting"
    : !animated ? "Movement paused" : `${work.mode === 'recent' ? 'Last action: ' : ''}${ACTIONS[work.kind]}`;
  const expand = async () => {
    setScreenNote("");
    try {
      if (document.fullscreenElement === scene.current) await document.exitFullscreen();
      else await scene.current?.requestFullscreen();
    } catch { setScreenNote("Full screen is unavailable here. You can still resize the window."); }
  };

  return <section className="office-panel" aria-labelledby="office-title">
    <header className="office-heading">
      <div><p className="office-eyebrow">YOUR WORKSPACE</p><h2 id="office-title">{name || "Drift"}'s office</h2></div>
      <label className="office-motion"><input type="checkbox" checked={animated && !reduced}
        disabled={reduced} onChange={event => {
          setAnimated(event.target.checked);
          try { localStorage.setItem('drift-office-motion', event.target.checked ? 'on' : 'off'); } catch { /* Optional preference. */ }
        }} />Office movement</label>
    </header>
    <div className={`office-scene${closeUp ? ' office-close-up' : ''}`} ref={scene}>
      <div className="office-visual">
        <OfficeCanvas status={status} animated={animated && !reduced}
          label={`Shaded panda in a furnished isometric studio. ${caption}. ${ACTIONS[work.kind]}. Poses illustrate reported activity, not exact progress.`} />
        <div className="office-view-tools">
          <button type="button" aria-pressed={closeUp} onClick={() => setCloseUp(value => !value)}>{closeUp ? 'Back to room' : 'Closer look · real work'}</button>
          {document.fullscreenEnabled && <button type="button" aria-pressed={expanded}
            onClick={() => { void expand(); }}>{expanded ? "Exit full screen" : "Expand office"}</button>}
        </div>
      </div>
      {closeUp && <DeskView connected={connected} work={work} savedTask={savedTask} project={deskProject} headers={headers} onProject={onProject} onReport={reportReceived} />}
    </div>
    <div className="office-caption">
      <p role="status"><span className={`office-status-dot${connected ? " office-connected" : ""}`} aria-hidden="true" />{caption}</p>
      <span>{motionCaption}</span>
    </div>
    {screenNote && <p className="office-note" role="status">{screenNote}</p>}
    <p className="office-note">Panda poses illustrate live or recently reported actions; they are not a progress meter. Closer look opens actual task data and saved reports, never a pretend project. Pausing movement does not stop work. Hidden tabs pause animation.</p>
  </section>;
}
