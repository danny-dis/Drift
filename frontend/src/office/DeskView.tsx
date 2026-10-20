import { useEffect, useState } from 'react';
import type { OfficeWork, WorkTask, WorkProject } from './work-context';

type Props = { connected: boolean; work: OfficeWork; savedTask?: WorkTask; project?: WorkProject; headers: () => Record<string,string>; onProject: (id: string) => void; onReport: (id: string, text: string) => void };

export default function DeskView({ connected, work, savedTask, project, headers, onProject, onReport }: Props) {
  const task = work.mode === 'idle' ? savedTask : work.task;
  const [report, setReport] = useState<{id: string; text: string; truncated: boolean} | null>(null);
  const [note, setNote] = useState('');
  useEffect(() => {
    setReport(null); setNote('');
    if (!task) return;
    if (task.status !== 'complete' && !task.last_evidence) { setNote('No saved report for this task yet.'); return; }
    const controller = new AbortController();
    fetch(`/api/ui/tasks/${encodeURIComponent(task.id)}/report`, { headers: headers(), signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('No saved report is available for this task.');
        const data = await response.json();
        if (typeof data.text !== 'string') throw new Error('The saved report could not be read.');
        setReport({ id: task.id, text: data.text, truncated: Boolean(data.truncated) }); onReport(task.id, data.text);
      }).catch(error => { if (!controller.signal.aborted) setNote(error instanceof Error ? error.message : 'Could not read saved work.'); });
    return () => controller.abort();
  }, [task?.id, task?.status, task?.last_evidence, headers, onReport]);
  return <section className="office-workbench" aria-labelledby="office-desk-title">
    <p className="office-eyebrow">{!connected ? 'OFFLINE · LAST KNOWN WORK' : work.mode === 'live' ? 'LIVE WORK' : work.mode === 'recent' ? 'LAST OBSERVED ACTION' : 'SAVED WORK · NOT RUNNING'}</p>
    <h3 id="office-desk-title">On Drift's desk</h3>
    {project ? <p className="office-project-name">{work.mode === 'idle' ? 'Saved project · ' : ''}{project.name}</p> : <p>{work.mode === 'idle' ? 'No project is active right now.' : 'This activity is not linked to a registered project.'}</p>}
    {work.target && <p>Observed target: <code>{work.target}</code></p>}
    {work.at && <p className="office-work-meta">Observed {new Date(work.at).toLocaleString()}</p>}
    {task ? <>
      <h4>{work.mode === 'idle' ? 'A saved task' : 'Actual task'}</h4>
      <p className="office-task-source">{task.source_text || task.goal}</p>
      <p className="office-work-meta">{task.id} · {task.status}</p>
      {!report && !note && <p role="status">Opening the saved report…</p>}
      {note && <p role="status">{note}</p>}
      {report?.id === task.id && <>
        <h4>Actual saved report</h4>
        <p className="office-work-meta">Unverified AI suggestions. This is saved content, not a live editor or browser video.</p>
        <pre className="office-document" tabIndex={0}>{report.text}</pre>
        {report.truncated && <p>Preview limited to the first 12,000 characters.</p>}
      </>}
    </> : <p>{work.mode === 'idle' ? 'Save a thought or start work from a registered project. Its real task and saved report will appear here.' : 'The backend reported activity but has not supplied a matching saved task. No project screen is invented.'}</p>}
    {project && <button type="button" onClick={() => onProject(project.id)}>Open this project</button>}
  </section>;
}
