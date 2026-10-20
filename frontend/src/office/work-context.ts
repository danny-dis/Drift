import type { OfficeActivity } from './motion';
export type WorkActivity = { kind?: string; active?: boolean; task_id?: string | null; project_id?: string | null; target?: string | null; at?: string | null };
export type WorkTask = { id: string; goal: string; status: string; last_evidence?: string; project_id?: string | null; source_text?: string; capture_id?: string };
export type WorkProject = { id: string; name: string; local_path?: string; repo?: string };
export type OfficeWork = { kind: OfficeActivity; mode: 'live' | 'recent' | 'idle'; task?: WorkTask; project?: WorkProject; target?: string | null; at?: string | null };
const KINDS = new Set(['idle','browsing','writing','reading','thinking','waiting']);

export function officeWork(state: string, current: WorkActivity | null | undefined, last: WorkActivity | null | undefined, tasks: WorkTask[], projects: WorkProject[], now: number): OfficeWork {
  let event = current?.active === true && KINDS.has(current.kind || '') ? current : undefined;
  let mode: OfficeWork['mode'] = event ? 'live' : 'idle';
  const age = now - Date.parse(last?.at || '');
  const readingNotes = event?.kind === 'thinking' && last?.kind === 'reading' && Boolean(last.task_id) && last.task_id === event.task_id;
  if (((!event && state === 'idle') || readingNotes) && last && ['writing','reading','browsing'].includes(last.kind || '') && age >= 0 && age < 12000) {
    event = last; mode = 'recent';
  }
  const busy = ['thinking','reflecting','planning','observing','researching'].includes(state);
  const kind = event?.kind as OfficeActivity | undefined || (busy ? 'thinking' : ['blocked','blocked_task','sleeping'].includes(state) ? 'waiting' : 'idle');
  if (!event) return { kind, mode: busy ? 'live' : 'idle' };
  const task = tasks.find(task => task.id === event.task_id);
  const projectId = event.project_id || task?.project_id;
  return { kind, mode, task, project: projects.find(project => project.id === projectId), target: event.target, at: event.at };
}
