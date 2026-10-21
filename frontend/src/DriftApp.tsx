import { useCallback, useEffect, useRef, useState } from "react";
import {parseRoute, routeHref, SECTIONS, type Section} from './navigation';
import EntityScreen from './EntityScreen';
import MindMap from './MindMap';
import WikiScreen from './WikiScreen';
import "./drift.css";
import "./ux.css";
import ThoughtInbox from "./ThoughtInbox";
import ThoughtInsights from "./ThoughtInsights";
import BudgetSummary from "./BudgetSummary";
import OfficePanel from "./OfficePanel";
import { officeWork, type WorkActivity } from "./office/work-context";
import SetupGuide from "./SetupGuide";
import type { SetupStatus } from "./SetupGuide";
import SectionTabs from "./SectionTabs";
import { createSessionTokenStore } from "./session-token";

const sessionToken = createSessionTokenStore(() => sessionStorage);

// Blast radius: imported only by main.tsx. No backend symbols touched.
// Talks to backend only via /api/* fetch. No direct host access.

type Idea = { id: string; text: string; status: string; concepts?: string[]; related_projects?: string[]; confidence?: number };
type Project = { id: string; name: string; repo: string; local_path?: string; importance?: number; last_seen_commit?: string; last_round?: string };
type Status = { state?: string; activity?: WorkActivity; last_activity?: WorkActivity; thought_count?: number; memory_count?: number; model?: string; name?: string; animal?: string; focus_mode?: boolean; [k: string]: unknown };
type EvidenceItem = { summary: string; evidence: { url?: string; title?: string; quote?: string }[]; confidence: number; source: string; timestamp: string };
type Candidate = { source: string; description: string; project_id: string; base_priority: number; estimated_cost: number };
type Receipt = { task_id: string; estimated_tokens: number; estimated_cost: number; model_provider: string; timestamp: string; context_budget?: number };
type Approval = { id: string; goal: string; objective?: string; project_id?: string; blockers?: string[]; phase?: string };
type Session = { id: string; query: string; state: string; phase?: string; next_action?: string; rev?: number; repairs?: number; project_id?: string; errors?: string[]; query_history?: unknown[]; notes?: unknown[]; tools?: unknown[]; scripts?: unknown[]; file_changes?: unknown[]; report_attempts?: unknown[]; repair_context?: unknown[]; sources?: {id: string; url: string; excerpt: string}[]; report?: {findings?: string[]; citations?: {source_id: string; quote?: string}[]} | null };
type Decisions = { loop: Record<string, unknown>; memory: Record<string, unknown> };
type Task = {id: string; goal: string; status: string; phase: string; project_id?: string; last_evidence?: string; blockers?: string[]; source_text?: string; capture_id?: string};

type Tab = Section;
const TABS = SECTIONS;

function authHeaders(): Record<string, string> {
  const t = sessionToken.read();
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

function isHttp(url: string): boolean {
  return url.startsWith("https://") || url.startsWith("http://");
}

export default function DriftApp() {
  const [route, setRoute] = useState(() => parseRoute(typeof window === 'undefined' ? '' : window.location.hash));
  const tab = route.section;
  const setTab = (section:Tab) => { window.location.hash = routeHref({section}); };
  useEffect(() => {
    const changed = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);
  useEffect(() => {
    const focused = document.activeElement;
    if (focused?.getAttribute('role') !== 'tab' && focused?.tagName !== 'SELECT') document.getElementById(`drift-panel-${tab}`)?.focus();
  }, [tab, route.id]);
  const [token, setToken] = useState(() => sessionToken.read());
  const [tokenNote, setTokenNote] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [setupError, setSetupError] = useState("");
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [statusErr, setStatusErr] = useState("");
  const [statusLoading, setStatusLoading] = useState(true);
  const [identity, setIdentity] = useState<{ name?: string; animal?: string }>({});
  const [resourceErrors, setResourceErrors] = useState<Record<string,string>>({});
  const [allLoading, setAllLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [findings, setFindings] = useState<{ summary: string; confidence?: number; timestamp?: string; evidence?: unknown }[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [budget, setBudget] = useState<Record<string, unknown>>({});
  const [decisions, setDecisions] = useState<Decisions | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidatesUnavailable, setCandidatesUnavailable] = useState(false);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [receiptTotal, setReceiptTotal] = useState<number | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionDetail, setSessionDetail] = useState<Session | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskReport, setTaskReport] = useState("");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const reportRegion = useRef<HTMLElement>(null);
  const [sessionsNote, setSessionsNote] = useState("");

  // forms (inputs preserved on failed capture)
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [sessQ, setSessQ] = useState("");
  const [sessUrls, setSessUrls] = useState("");
  const [sessProj, setSessProj] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status", { headers: authHeaders() });
      if (!res.ok) {
        if (res.status === 401) { setAuthRequired(true); setSettingsOpen(true); }
        setStatusErr(`status ${res.status}`); return;
      }
      setStatus(await res.json()); setStatusErr("");
    } catch (e) { setStatusErr(String(e)); } finally { setStatusLoading(false); }
  }, []);

  const loadAll = useCallback(async () => {
    const failures: Record<string,string> = {};
    setAllLoading(true);
    const get = async (url: string) => {
      try {
        const res = await fetch(url, { headers: authHeaders() });
        if (!res.ok) {
          if (res.status === 401) { setAuthRequired(true); setSettingsOpen(true); }
          failures[url] = `${url}: ${res.status}${res.status === 401 ? " — session token required" : " — data unavailable"}`;
          return null; // do not pretend unavailable fields work
        }
        return await res.json();
      } catch { failures[url] = `${url}: cannot reach Drift`; return null; }
    };
    const [id, ip, uj, rs, ev, bg, cd, rc, ap, ss, ts, dc] = await Promise.all([
      get("/api/identity"), get("/api/ui/ideas"), get("/api/ui/projects"),
      get("/api/ui/research"), get("/api/ui/research/evidence"), get("/api/ui/budget"),
      get("/api/ui/attention/candidates"), get("/api/ui/receipts"), get("/api/ui/approvals"),
      get("/api/ui/research/sessions"), get("/api/ui/tasks"), get("/api/ui/decisions"),
    ]);
    setDecisions(dc || null);
    if (ts) setTasks(ts.tasks || []);
    if (id) setIdentity(id);

    if (uj) setProjects(uj.projects || []);
    if (rs) setFindings(rs.findings || []);
    if (ev) setEvidence(ev.evidence || []);
    if (bg) setBudget(bg);
    setCandidatesUnavailable(!cd);
    if (cd) setCandidates(cd.candidates || []);
    if (rc) { setReceipts(rc.receipts || []); setReceiptTotal(rc.total_estimated_cost ?? null); }
    if (ap) setApprovals(ap.pending || []);
    if (ss && ss.sessions) {
      setSessions(ss.sessions);
      setSessionsNote(current => current === "Research sessions unavailable; check backend/authentication" ? "" : current);
    }
    else setSessionsNote("Research sessions unavailable; check backend/authentication");
    setResourceErrors(failures);setAllLoading(false);
  }, []);

  const loadSetup = useCallback(async () => {
    try {
      const res = await fetch("/api/ui/setup", { headers: authHeaders() });
      if (!res.ok) {
        setSetup(null);
        if (res.status === 401) {
          setAuthRequired(true); setSettingsOpen(true);
          setSetupError("Drift requires its API session token. Open Connection settings; your draft is unchanged.");
        } else setSetupError("Setup status unavailable. You can still write a draft and try saving.");
        return;
      }
      setSetup(await res.json()); setSetupError(""); setAuthRequired(false);
    } catch {
      setSetup(null); setSetupError("Cannot reach Drift for setup status. Your draft is unchanged.");
    }
  }, []);

  const checkConnection = async () => {
    if (checking) return;
    setChecking(true); setSetupError("");
    try {
      const res = await fetch("/api/ui/setup/check", { method: "POST", headers: authHeaders(), body: "{}" });
      if (!res.ok) {
        if (res.status === 401) {
          setAuthRequired(true); setSettingsOpen(true);
          setSetupError("Save your Drift API session token in Connection settings, then retry the check.");
        } else setSetupError("AI check could not finish. Saving thoughts is separate; retry only when you choose.");
        return;
      }
      setSetup(await res.json()); setAuthRequired(false);
      await loadAll();
    } catch { setSetupError("Cannot reach Drift for the AI check. Your draft is unchanged."); }
    finally { setChecking(false); }
  };

  const saveToken = async () => {
    try {
      const persisted = sessionToken.write(token);
      const note = persisted ? "Token saved for this browser session." : "Browser storage is blocked. The token applies only until this page reloads; saved thoughts are unaffected.";
      setTokenNote(note); setMsg(note);
      setHistoryRevision(value => value + 1);
      await Promise.all([loadStatus(), loadAll(), loadSetup()]);
    } catch { setErr("Connection status could not be refreshed. Your draft is unchanged."); }
  };

  useEffect(() => { loadStatus(); loadAll(); loadSetup(); }, [loadStatus, loadAll, loadSetup]);
  useEffect(() => { const t = setInterval(loadAll, 15000); return () => clearInterval(t); }, [loadAll]);
  useEffect(() => {
    const poll = () => {
      if (document.hidden) return;
      void loadStatus();
      if (tab === 'office') fetch('/api/ui/tasks', { headers: authHeaders() }).then(async response => {
        if (response.ok) { const data = await response.json(); if (Array.isArray(data.tasks)) setTasks(data.tasks); }
      }).catch(() => {});
    };
    if (tab === 'office') poll();
    const t = setInterval(poll, tab === 'office' ? 2000 : 10000);
    return () => clearInterval(t);
  }, [loadStatus, tab]);
  useEffect(() => { if (activeTaskId) reportRegion.current?.focus(); }, [activeTaskId]);

  const createSession = async () => {
    if (!sessQ.trim()) return;
    setSessionsNote(""); setErr("");
    try {
      const body: Record<string, unknown> = { query: sessQ };
      const urls = sessUrls.split(",").map(s => s.trim()).filter(Boolean);
      if (urls.length) body.urls = urls;
      if (sessProj.trim()) body.project_id = sessProj.trim();
      const res = await fetch("/api/ui/research/sessions", { method: "POST", headers: authHeaders(), body: JSON.stringify(body) });
      if (!res.ok) {
        if (res.status === 404 || res.status === 405) setSessionsNote("Research endpoint unavailable — input kept");
        else setSessionsNote(`session create failed: ${res.status} — input kept`);
        return;
      }
      setSessQ(""); setSessUrls(""); setMsg("research session created");
      await loadAll();
    } catch (e) { setSessionsNote(`session create failed: ${String(e)} — input kept`); }
  };

  const openSession = async (id: string) => {
    try {
      const res = await fetch(`/api/ui/research/sessions/${id}`, { headers: authHeaders() });
      if (!res.ok) { setSessionsNote(`session ${id}: ${res.status}`); return; }
      const data = await res.json(); setSessionDetail(data.session);
    } catch (e) { setSessionsNote(String(e)); }
  };

  const resumeSession = async (id: string) => {
    try {
      const res = await fetch(`/api/ui/research/sessions/${id}/resume`, {method: "POST", headers: authHeaders(), body: "{}"});
      const data = await res.json();
      if (!res.ok) { setSessionsNote(`Resume rejected: ${data.detail || res.status}`); return; }
      setSessionDetail(data.session); setSessionsNote("Same task queued for repair; evidence retained.");
      await loadAll();
    } catch (e) { setSessionsNote(`Resume failed: ${String(e)}`); }
  };

  const openTaskReport = async (id: string) => {
    try {
      const res = await fetch(`/api/ui/tasks/${id}/report`, {headers: authHeaders()});
      if (!res.ok) { setTaskReport("Report unavailable; task may not have finished."); return; }
      setTaskReport((await res.json()).text);
    } catch (e) { setTaskReport(String(e)); }
  };

  const approve = async (id: string) => {
    setErr("");
    try {
      const res = await fetch(`/api/ui/approvals/${id}/approve`, { method: "POST", headers: authHeaders(), body: "{}" });
      if (!res.ok) { setErr(`approve failed: ${res.status}`); return; }
      setMsg(`approved ${id}`);
      const d = await (await fetch("/api/ui/approvals", { headers: authHeaders() })).json();
      setApprovals(d.pending || []);
    } catch (e) { setErr(`approve failed: ${String(e)}`); }
  };

  const screenResources: Partial<Record<Tab,string[]>> = {
    office:['/api/ui/tasks'],research:['/api/ui/research','/api/ui/research/evidence','/api/ui/research/sessions'],
    attention:['/api/ui/tasks','/api/ui/budget','/api/ui/attention/candidates','/api/ui/receipts','/api/ui/decisions'],
    approvals:['/api/ui/approvals'],
  };
  const screenFailures = (screenResources[tab]||[]).map(path=>resourceErrors[path]).filter(Boolean);
  const screenError = screenFailures.length > 0;
  const activeTask = tasks.find(task => task.id === activeTaskId);
  const work = officeWork(String(status?.state || 'unknown'), status?.activity, status?.last_activity, tasks, projects, Date.now());
  const savedTask = [...tasks].reverse().find(task => task.status === 'complete' && task.last_evidence);

  return (
    <main className="drift-shell">
      <a className="skip-link" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById(`drift-panel-${tab}`)?.focus();}}>Skip to page content</a>
      <header className="topbar">
        <div><h1 className="brand">DRIFT</h1><span className="tagline">Save thoughts now. Make sense of them later.</span></div>
        <div className="status" aria-live="polite">
          {statusLoading ? "Connecting to workspace…" : statusErr ? statusErr.includes("401") || statusErr.includes("403") ? "Drift API token required" : "Workspace unavailable" : status ? "Workspace connected" : "Workspace unavailable"}
        </div>
      </header>

      <SectionTabs tabs={TABS} selected={tab} onSelect={setTab} />

      <div className="workspace-tools"><SetupGuide setup={setup} error={setupError} checking={checking}
        onCheck={() => { void checkConnection(); }} onSuggestions={() => setTab("inbox")} />

      <details className="connection-settings" open={settingsOpen} onToggle={event => setSettingsOpen(event.currentTarget.open)}>
        <summary>Connection settings{authRequired ? " — API token needed" : " (optional)"}</summary>
        {authRequired && <p className="error" role="alert">Drift returned 401. Enter the Drift API session token, then save settings to reload status and history. Your draft stays here.</p>}
        <section className="auth-row" aria-label="API authentication">
        <label htmlFor="drift-token">Drift API token (this browser session):</label>
        <input id="drift-token" type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Drift API session token" autoComplete="off" />
        <button type="button" onClick={() => { void saveToken(); }}>Save token</button>
        <small>{tokenNote || "Kept for this browser session and sent as an Authorization header. Never enter provider secrets here."}</small>
        </section>
      </details>

      </div>

      {screenResources[tab] && allLoading && <p role="status">Loading page data…</p>}
      {screenError && <div role="alert" className="resource-error"><p>Page data could not be refreshed. Previously loaded records may be stale; unavailable data is not an empty result.</p><ul>{screenFailures.map(message=><li key={message}>{message}</li>)}</ul><button onClick={()=>void loadAll()} disabled={allLoading}>Retry page data</button></div>}
      {msg && <div className="hint" role="status">{msg}</div>}
      {err && <div className="error" role="alert">{err}</div>}

      {TABS.filter(t => t.id !== tab).map(t => <section key={t.id} hidden role="tabpanel"
        id={`drift-panel-${t.id}`} aria-labelledby={`drift-tab-${t.id}`} />)}

      {tab === "status" && (
        <section role="tabpanel" id="drift-panel-status" aria-labelledby="drift-tab-status" tabIndex={0} className="panel">
          <h2 className="panel-title">Your workspace <span>{identity.name || "Drift"} · panda companion</span></h2>
          <div className="pad">
            <p className="page-intro">Check your workspace connection here. Saving thoughts is separate from optional AI processing.</p>
            <button className="primary" type="button" onClick={() => setTab("inbox")}>Write a thought</button>
            {statusLoading && <p>Loading live status…</p>}
            {statusErr && <p role="alert">Could not reach /api/status: {statusErr}. Backend may be down; no fields are faked.</p>}
            {status && (
              <ul>
                <li>Current activity: {String(status.state ?? "unknown")}</li>
                <li>Thoughts processed since restart: {String(status.thought_count ?? "n/a")}</li>
                <li>Saved memory items: {String(status.memory_count ?? "n/a")}</li>
                <li><details><summary>Technical connection details</summary><p>Configured model/route: {String(status.model ?? "n/a")} (availability is separate from saving)</p><p>Focus mode: {String(status.focus_mode ?? "n/a")}</p></details></li>
              </ul>
            )}
            <p><small>Status refreshes every 10 seconds without calling AI. Unavailable fields are shown as n/a. AI may use a remote provider; see Getting started for configured access and privacy details.</small></p>
          </div>
        </section>
      )}

      {(['inbox','ideas','projects'] as string[]).includes(tab) && (
        <section role="tabpanel" id={`drift-panel-${tab}`} aria-labelledby={`drift-tab-${tab}`} tabIndex={-1} className="panel">
          <EntityScreen key={tab} kind={tab === 'inbox' ? 'thought' : tab === 'ideas' ? 'idea' : 'project'} id={route.id} headers={authHeaders} refreshKey={historyRevision}
            composer={<ThoughtInbox composerOnly headers={authHeaders} refreshKey={historyRevision} onCaptured={() => {setHistoryRevision(value=>value+1);void loadAll();}}/>}/>
        </section>
      )}
      {tab === 'mind-map' && <section role="tabpanel" id="drift-panel-mind-map" aria-labelledby="drift-tab-mind-map" tabIndex={-1} className="panel"><MindMap headers={authHeaders}/></section>}
      {tab === 'wiki' && <section role="tabpanel" id="drift-panel-wiki" aria-labelledby="drift-tab-wiki" tabIndex={-1} className="panel"><WikiScreen id={route.id} headers={authHeaders}/></section>}

      {tab === "office" && (
        <section role="tabpanel" id="drift-panel-office" aria-labelledby="drift-tab-office" tabIndex={0}>
          <OfficePanel state={String(status?.state ?? "unknown")} name={identity.name || "Drift"}
            connected={Boolean(status) && !statusErr} work={work} savedTask={savedTask} savedProject={projects.find(item => item.id === savedTask?.project_id)} headers={authHeaders}
            onProject={id => { window.location.hash=routeHref({section:'projects',id}); }} />
        </section>
      )}

      {tab === "research" && (
        <section role="tabpanel" id="drift-panel-research" aria-labelledby="drift-tab-research" tabIndex={0} className="panel">
          <h2 className="panel-title">Research</h2>
          <div className="pad">
            <p className="page-intro">Explore a question and review the sources behind the answer. AI findings are suggestions, not verified facts.</p>
            <a className="next-step" href="#research-start">Start with a research question ↓</a>
            <details className="advanced-details"><summary>Saved findings & source evidence ({findings.length} findings)</summary>
            <h3>Findings ({findings.length})</h3>
            {!allLoading && !screenError && findings.length === 0 && <p>No findings to show yet. Start a session below, or check the workspace connection if results are missing.</p>}
            <ul>{findings.slice(-10).map((f, k) => <li key={k}>{f.summary} <small>· confidence {f.confidence ?? "unverified"}</small></li>)}</ul>
            <h3>Sources & citations</h3>
            {!allLoading && !screenError && evidence.length === 0 && <p><small>No evidence yet — uncertain/unverified until backend reports it.</small></p>}
            <ul>
              {evidence.slice(-10).map((e, k) => (
                <li key={k}>
                  <p>{e.summary} {(e.confidence ?? 0) < 0.5 && <em>· uncertain/unverified</em>} <small>({e.source || "unknown source"} · {e.timestamp || "no timestamp"})</small></p>
                  <ul>
                    {(e.evidence || []).map((c, j) => (
                      <li key={j}>
                        {c.title && <span>{c.title} — </span>}
                        {c.url && isHttp(c.url) ? <a href={c.url} target="_blank" rel="noreferrer">{c.url}</a> : c.url && <span>{c.url} (non-http, not linked)</span>}
                        {c.quote && <blockquote>{c.quote}</blockquote>}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
            </details>
            <h3 id="research-start">Start a research session</h3>
            <p className="helper">Starting a session queues AI work and may use your model-call allowance. Review its report before acting.</p>
            {sessionsNote && <p role="status">{sessionsNote}</p>}
            <form onSubmit={e => { e.preventDefault(); createSession(); }}>
              <label htmlFor="sess-q">What would you like to find out?</label>
              <input id="sess-q" value={sessQ} onChange={e => setSessQ(e.target.value)} required />
              <details className="form-options"><summary>Optional sources & project</summary>
              <label htmlFor="sess-urls">Source links (comma-separated)</label>
              <input id="sess-urls" value={sessUrls} onChange={e => setSessUrls(e.target.value)} />
              <label htmlFor="sess-proj">Project id (optional)</label>
              <input id="sess-proj" value={sessProj} onChange={e => setSessProj(e.target.value)} />
              </details>
              <button className="primary" type="submit">Start research</button>
            </form>
            <h3>Your sessions</h3>
            {!allLoading && !screenError && sessions.length === 0 && <p className="empty-state">No sessions to show. Your question above is the starting point; connection errors will appear here if sessions cannot load.</p>}
            <ul>{sessions.map(s => <li key={s.id}><button onClick={() => openSession(s.id)}>{s.query} <small>({s.state || "unknown"})</small></button></li>)}</ul>
            {sessionDetail && <article aria-label="Research report">
              <h3>{sessionDetail.query}</h3>
              <p>Status: {sessionDetail.state}. Citation integrity is not fact verification.</p>
              <p>Phase: {sessionDetail.phase || "unavailable"} · next action: {sessionDetail.next_action || "unavailable"} · checkpoint revision: {sessionDetail.rev ?? "unavailable"}</p>
              <button onClick={() => openSession(sessionDetail.id)}>Refresh report</button>
              {sessionDetail.state === "needs_review" && <button onClick={() => resumeSession(sessionDetail.id)}>Resume same task for repair</button>}
              <details><summary>Retained research provenance</summary><pre>{JSON.stringify({query_history: sessionDetail.query_history, notes: sessionDetail.notes, tools: sessionDetail.tools, scripts: sessionDetail.scripts, file_changes: sessionDetail.file_changes, report_attempts: sessionDetail.report_attempts, repair_context: sessionDetail.repair_context}, null, 2).slice(0, 18000)}</pre></details>
              <ul>{sessionDetail.errors?.map((e,k) => <li key={k}>{e}</li>)}</ul>
              <ul>{sessionDetail.report?.findings?.map((f,k) => <li key={k}>{f}</li>)}</ul>
              {sessionDetail.report?.citations?.map((c,k) => {
                const source = sessionDetail.sources?.find(s => s.id === c.source_id);
                return <div key={k}>{source && isHttp(source.url) && <a href={source.url} target="_blank" rel="noreferrer">{source.url}</a>}{c.quote && <blockquote>{c.quote}</blockquote>}</div>;
              })}
              <details><summary>Retained sources</summary><ul>{sessionDetail.sources?.map(s => <li key={s.id}>{s.url}: {s.excerpt}</li>)}</ul></details>
              {!sessionDetail.report && <p>No valid report yet; review errors or wait for queued work.</p>}
            </article>}
          </div>
        </section>
      )}

      {tab === "attention" && (
        <section role="tabpanel" id="drift-panel-attention" aria-labelledby="drift-tab-attention" tabIndex={0} className="panel">
          <h2 className="panel-title">Activity & budget</h2>
          <div className="pad">
            <p className="page-intro">See what Drift is working on and how much AI allowance remains. Saving thoughts does not require a model call.</p>
            <h3>Tasks</h3>
            {!allLoading && !screenError && tasks.length === 0 && <p className="empty-state">No tasks to show. You can keep saving thoughts in your inbox; if activity seems missing, check the workspace connection.</p>}
            <button type="button" onClick={() => setTab("approvals")}>Review pending approvals</button>
            <ul>{tasks.map(t => <li className="task-row" key={t.id}>
              <p className="task-summary">{t.source_text || t.goal}</p>
              <small>{t.status === "complete" ? "Suggestions ready for review" : t.status === "blocked" ? "Needs your review" : t.status}</small>{" "}
              {t.last_evidence && <button aria-label={`View suggestions for ${(t.source_text || t.goal).slice(0, 60)}`} onClick={() => {
                setActiveTaskId(t.id); setTaskReport("");
                if (!t.capture_id) void openTaskReport(t.id);
              }}>View suggestions</button>}
              {t.blockers?.length ? <p className="helper">{t.blockers.join("; ")}</p> : null}
            </li>)}</ul>
            {activeTask && <section ref={reportRegion} tabIndex={-1} className="saved-suggestions" aria-label="Saved task suggestions">
              <h3>Saved suggestions</h3>
              {activeTask.capture_id ? <ThoughtInsights key={activeTask.capture_id} captureId={activeTask.capture_id} status={activeTask.status} headers={authHeaders} />
                : taskReport ? <pre>{taskReport}</pre> : <p role="status">Loading saved report…</p>}
            </section>}
            <details className="advanced-details"><summary>Advanced: recorded decisions</summary>
            {decisions ? <>
              <p>Recorded loop and memory decisions; keyword gates are not semantic judgments. Unmeasured metrics remain unavailable.</p>
              <details><summary>Loop decisions</summary><pre>{JSON.stringify(decisions.loop, null, 2)}</pre></details>
              <details><summary>Memory decision summary (no raw memory)</summary><pre>{JSON.stringify(decisions.memory, null, 2)}</pre></details>
            </> : <p>Decision telemetry unavailable; check backend/authentication.</p>}
            </details>
            <h3>Budget</h3>
            {Object.keys(budget).length === 0 ? <p><small>No budget data (backend unavailable).</small></p> : (
              <BudgetSummary value={budget} />
            )}
            <details className="advanced-details"><summary>Proposed tasks & estimated usage</summary>
            <h3>Proposed tasks (why each matters)</h3>
            {candidatesUnavailable ? <p role="alert">Attention candidates unavailable; check backend/authentication. Previously loaded candidates may be stale.</p>
              : candidates.length === 0 && <p><small>No candidates queued.</small></p>}
            <ul>
              {candidates.map((c, k) => (
                <li key={k}><b>{c.source}</b> — {c.description} <small>· project {c.project_id || "none"} · priority {c.base_priority} · cost {c.estimated_cost}</small></li>
              ))}
            </ul>
            <h3>Usage estimates {receiptTotal !== null && <small>· total {receiptTotal}</small>}</h3>
            <p className="helper">Recorded estimates are not billing receipts.</p>
            <ul>{receipts.slice(-10).map((r, k) => <li key={k}><small>{r.task_id} · {r.estimated_tokens} tok · {r.estimated_cost} · {r.model_provider} · {r.timestamp}</small></li>)}</ul>
            </details>
          </div>
        </section>
      )}

      {tab === "approvals" && (
        <section role="tabpanel" id="drift-panel-approvals" aria-labelledby="drift-tab-approvals" tabIndex={0} className="panel">
          <h2 className="panel-title">Needs your approval <span>{approvals.length} pending</span></h2>
          <div className="pad">
            <p className="page-intro">Read each task and its blockers before approving. Approval authorizes that task to continue.</p>
            {!allLoading && !screenError && approvals.length === 0 && <div className="empty-state"><p>No approvals to show. If the workspace is connected, there is nothing here to approve right now.</p><button type="button" onClick={() => setTab("inbox")}>Back to your inbox</button></div>}
            <ul>
              {approvals.map(a => (
                <li key={a.id}>
                  <p><b>{a.goal}</b> <small>· {a.phase || "blocked"} · project {a.project_id || "none"}</small></p>
                  {(a.blockers || []).length > 0 && <p><small>Blockers: {(a.blockers || []).join("; ")}</small></p>}
                  <button aria-label={`Approve task: ${a.goal}`} onClick={() => approve(a.id)}>Approve task</button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <footer><small>Backend owns saved data; browser drafts stay in local storage. AI may use remote providers. Generated reports require owner review. Sources and model output are untrusted.</small></footer>
    </main>
  );
}
