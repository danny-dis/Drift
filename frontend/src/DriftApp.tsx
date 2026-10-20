import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./drift.css";
import ThoughtInbox from "./ThoughtInbox";
import ThoughtInsights from "./ThoughtInsights";
import BudgetSummary from "./BudgetSummary";
import ProjectIntelligence from "./ProjectIntelligence";
import OfficePanel from "./OfficePanel";
import { officeWork, type WorkActivity } from "./office/work-context";
import { projectForNode } from "./project-navigation";
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

type Tab = "status" | "inbox" | "office" | "projects" | "research" | "attention" | "approvals";
const TABS: { id: Tab; label: string }[] = [
  { id: "inbox", label: "Inbox" },
  { id: "office", label: "Office" },
  { id: "projects", label: "Projects" },
  { id: "research", label: "Research" },
  { id: "attention", label: "Activity & budget" },
  { id: "approvals", label: "Needs approval" },
  { id: "status", label: "Workspace" },
];

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
  const [tab, setTab] = useState<Tab>("inbox");
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
  const [ideas, setIdeas] = useState<Idea[]>([]);
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
  const [selected, setSelected] = useState<{ kind: string; id: string; label: string; detail: string } | null>(null);
  const [projectDetail, setProjectDetail] = useState<{ events: { summary: string }[]; ideas: Idea[]; drift_md: string; intelligence?: Record<string, unknown> } | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const projectSequence = useRef(0);

  // forms (inputs preserved on failed capture)
  const [ideaText, setIdeaText] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [reg, setReg] = useState({ name: "", repo: "", local_path: "", importance: "0.5" });
  const [regNote, setRegNote] = useState("");
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
    const get = async (url: string) => {
      try {
        const res = await fetch(url, { headers: authHeaders() });
        if (!res.ok) {
          if (res.status === 401) { setAuthRequired(true); setSettingsOpen(true); }
          return null; // do not pretend unavailable fields work
        }
        return await res.json();
      } catch { return null; }
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
    if (ip) setIdeas(ip.ideas || []);
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

  const submitIdea = async () => {
    if (!ideaText.trim()) return;
    setMsg("capturing…"); setErr("");
    try {
      const res = await fetch("/api/ui/ideas", { method: "POST", headers: authHeaders(), body: JSON.stringify({ text: ideaText }) });
      if (!res.ok) { setErr(`capture failed: ${res.status}`); return; } // preserve input
      setIdeaText(""); setMsg("idea captured");
      const d = await (await fetch("/api/ui/ideas", { headers: authHeaders() })).json();
      setIdeas(d.ideas || []);
    } catch (e) { setErr(`capture failed: ${String(e)}`); } // preserve input
  };

  const registerProject = async () => {
    setRegNote(""); setErr("");
    try {
      const body: Record<string, unknown> = { name: reg.name, repo: reg.repo };
      if (reg.local_path.trim()) body.local_path = reg.local_path.trim();
      const imp = parseFloat(reg.importance);
      if (!Number.isNaN(imp)) body.importance = imp;
      const res = await fetch("/api/ui/projects", { method: "POST", headers: authHeaders(), body: JSON.stringify(body) });
      if (!res.ok) {
        if (res.status === 404 || res.status === 405) setRegNote("Project endpoint unavailable — input kept");
        else setRegNote(`register failed: ${res.status} — input kept`);
        return; // preserve input
      }
      setReg({ name: "", repo: "", local_path: "", importance: "0.5" }); setRegNote("project registered");
      await loadAll();
    } catch (e) { setRegNote(`register failed: ${String(e)} — input kept`); }
  };

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

  const openProject = async (p: Project) => {
    const sequence = ++projectSequence.current;
    setProjectDetail(null); setProjectLoading(true);
    setSelected({ kind: "project", id: p.id, label: p.name, detail: `${p.repo}${p.local_path ? ` · ${p.local_path}` : ""}` });
    try {
      const res = await fetch(`/api/ui/projects/${p.id}`, { headers: authHeaders() });
      if (!res.ok) { if (sequence === projectSequence.current) setProjectDetail(null); return; }
      const d = await res.json();
      if (sequence !== projectSequence.current) return;
      setProjectDetail({ events: d.events || [], ideas: d.ideas || [], drift_md: d.drift_md || "", intelligence: d.intelligence || undefined });
    } catch { if (sequence === projectSequence.current) setProjectDetail(null); }
    finally { if (sequence === projectSequence.current) setProjectLoading(false); }
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

  // deterministic lightweight mind map (no graph lib)
  const nodes = useMemo(() => {
    const ns = [
      ...projects.slice(0, 12).map(p => ({ id: `p:${p.id}`, kind: "project", label: p.name })),
      ...ideas.slice(0, 12).map(i => ({ id: `i:${i.id}`, kind: "idea", label: i.text.slice(0, 42) })),
    ];
    return ns.slice(0, 24);
  }, [projects, ideas]);
  const edges = useMemo(() => {
    const e: { source: string; target: string; relation: string }[] = [];
    ideas.forEach(i => (i.related_projects || []).forEach(pid => { if (nodes.some(n => n.id === `p:${pid}`)) e.push({ source: `i:${i.id}`, target: `p:${pid}`, relation: "about" }); }));
    const ps = projects.slice(0, 12);
    for (let k = 1; k < ps.length; k++) e.push({ source: `p:${ps[k - 1].id}`, target: `p:${ps[k].id}`, relation: "shelf-order" });
    return e.slice(0, 32);
  }, [ideas, projects, nodes]);
  const pos = (idx: number) => ({ left: `${8 + ((idx * 37) % 84)}%`, top: `${12 + ((idx * 53) % 70)}%` });
  const activeTask = tasks.find(task => task.id === activeTaskId);
  const work = officeWork(String(status?.state || 'unknown'), status?.activity, status?.last_activity, tasks, projects, Date.now());
  const savedTask = [...tasks].reverse().find(task => task.status === 'complete' && task.last_evidence);

  return (
    <main className="drift-shell">
      <header className="topbar">
        <div><h1 className="brand">DRIFT</h1><span className="tagline">Save thoughts now. Make sense of them later.</span></div>
        <div className="status" aria-live="polite">
          {statusLoading ? "Connecting to workspace…" : statusErr ? statusErr.includes("401") || statusErr.includes("403") ? "Drift API token required" : "Workspace unavailable" : status ? "Workspace connected" : "Workspace unavailable"}
        </div>
      </header>

      <SetupGuide setup={setup} error={setupError} checking={checking}
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

      <SectionTabs tabs={TABS} selected={tab} onSelect={setTab} />

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

      {tab === "inbox" && (
        <section role="tabpanel" id="drift-panel-inbox" aria-labelledby="drift-tab-inbox" tabIndex={0} className="panel">
          <ThoughtInbox headers={authHeaders} refreshKey={historyRevision} onCaptured={() => { void loadAll(); }} />
          <details className="pad"><summary>Earlier ideas and project links</summary>
            <label htmlFor="idea-box">Capture an idea (input kept if capture fails):</label>
            <textarea id="idea-box" value={ideaText} onChange={e => setIdeaText(e.target.value)} placeholder="Half-formed is fine…" />
            <button className="primary" onClick={submitIdea}>+ Capture idea</button>
            <ul>
              {ideas.slice().reverse().slice(0, 20).map(i => (
                <li key={i.id}>
                  <button className="idea" onClick={() => setSelected({ kind: "idea", id: i.id, label: i.text.slice(0, 60), detail: `status ${i.status} · confidence ${i.confidence ?? "unverified"} · concepts ${(i.concepts || []).join(", ") || "none"}` })}>
                    <b>{i.status}</b> {i.text} {(i.confidence ?? 0) < 0.5 && <em> · uncertain/unverified</em>}
                  </button>
                </li>
              ))}
            </ul>
            {selected?.kind === "idea" && <p tabIndex={0} aria-live="polite"><b>Selected idea:</b> {selected.label} — {selected.detail}</p>}
          </details>
        </section>
      )}

      {tab === "office" && (
        <section role="tabpanel" id="drift-panel-office" aria-labelledby="drift-tab-office" tabIndex={0}>
          <OfficePanel state={String(status?.state ?? "unknown")} name={identity.name || "Drift"}
            connected={Boolean(status) && !statusErr} work={work} savedTask={savedTask} savedProject={projects.find(item => item.id === savedTask?.project_id)} headers={authHeaders}
            onProject={id => { const project = projects.find(item => item.id === id); if (project) { void openProject(project); setTab('projects'); } }} />
        </section>
      )}

      {tab === "projects" && (
        <section role="tabpanel" id="drift-panel-projects" aria-labelledby="drift-tab-projects" tabIndex={0} className="panel">
          <h2 className="panel-title">Your projects <span>{projects.length} registered</span></h2>
          <div className="pad">
            <p className="page-intro">Keep related ideas and findings together. Add a project, then select it below to review its briefing.</p>
            <h3>Add a project</h3>
            <form onSubmit={e => { e.preventDefault(); registerProject(); }}>
              <label htmlFor="reg-name">Name</label>
              <input id="reg-name" value={reg.name} onChange={e => setReg({ ...reg, name: e.target.value })} required />
              <details className="form-options"><summary>Optional project settings</summary>
              <label htmlFor="reg-repo">Code repository (optional)</label>
              <input id="reg-repo" value={reg.repo} onChange={e => setReg({ ...reg, repo: e.target.value })} placeholder="organization/repository" />
              <label htmlFor="reg-path">Project folder on this machine (optional)</label>
              <input id="reg-path" value={reg.local_path} onChange={e => setReg({ ...reg, local_path: e.target.value })} />
              <p className="helper">Use an existing folder allowed by this workspace. You can also keep a project here without linking a folder.</p>
              <label htmlFor="reg-imp">Priority (0 = lowest, 1 = highest)</label>
              <input id="reg-imp" value={reg.importance} onChange={e => setReg({ ...reg, importance: e.target.value })} type="number" min="0" max="1" step="0.1" />
              </details>
              <button className="primary" type="submit">Add project</button>
            </form>
            {regNote && <p role="status">{regNote}</p>}
            <h3>Project shelf</h3>
            {projects.length === 0 && <p className="empty-state">No projects to show yet. Use the form above to add one. If you expected projects here, check your workspace connection.</p>}
            <ul>
              {projects.map(p => (
                <li key={p.id}>
                  <button className="project" onClick={() => openProject(p)}><b>{p.name}</b> <small>{p.repo}{p.local_path ? ` · ${p.local_path}` : ""}</small></button>
                </li>
              ))}
            </ul>
            {selected?.kind === "project" && (
              <div tabIndex={0} aria-live="polite">
                <h3>Selected project: {selected.label}</h3>
                <p>{selected.detail}</p>
                {projectLoading ? <p role="status">Loading project details…</p> : projectDetail ? (
                  <>
                    <p>Related ideas: {projectDetail.ideas.length} · events: {projectDetail.events.length}</p>
                    <ProjectIntelligence projectId={selected.id} value={projectDetail.intelligence} headers={authHeaders} publishAvailable={Boolean(projects.find(p => p.id === selected.id)?.local_path)} />
                    <ul>{projectDetail.ideas.slice(0, 5).map(i => <li key={i.id}>{i.text}</li>)}</ul>
                    <details><summary>Saved drift.md summary</summary>{projectDetail.drift_md ? <pre>{projectDetail.drift_md.slice(0, 2000)}</pre> : <p><small>No drift.md summary available.</small></p>}</details>
                  </>
                ) : <p><small>Detail unavailable (backend returned no detail).</small></p>}
              </div>
            )}
            <details className="advanced-details"><summary>Project map & technical links</summary>
            <p className="helper">An overview of saved links, not an AI recommendation. The project shelf above is the easiest way to open a project.</p>
            <div className="map" aria-label="Deterministic mind map">
              <div className="map-center">DRIFT</div>
              {nodes.map((n, idx) => <button key={n.id} className={`node ${n.kind}`} style={pos(idx)} onClick={() => {
                const project = projectForNode(n.id, projects);
                if (project) { void openProject(project); return; }
                setSelected({ kind: n.kind, id: n.id.slice(2), label: n.label, detail: "idea node — see Inbox" });
              }}>{n.label.slice(0, 42)}</button>)}
            </div>
            <p><small>Edges ({edges.length}, deterministic, no graph lib):</small></p>
            <ul>{edges.slice(0, 10).map((e, k) => <li key={k}><small>{e.source} —{e.relation}→ {e.target}</small></li>)}</ul>
            </details>
          </div>
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
            {findings.length === 0 && <p>No findings to show yet. Start a session below, or check the workspace connection if results are missing.</p>}
            <ul>{findings.slice(-10).map((f, k) => <li key={k}>{f.summary} <small>· confidence {f.confidence ?? "unverified"}</small></li>)}</ul>
            <h3>Sources & citations</h3>
            {evidence.length === 0 && <p><small>No evidence yet — uncertain/unverified until backend reports it.</small></p>}
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
            {sessions.length === 0 && <p className="empty-state">No sessions to show. Your question above is the starting point; connection errors will appear here if sessions cannot load.</p>}
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
            {tasks.length === 0 && <p className="empty-state">No tasks to show. You can keep saving thoughts in your inbox; if activity seems missing, check the workspace connection.</p>}
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
            {approvals.length === 0 && <div className="empty-state"><p>No approvals to show. If the workspace is connected, there is nothing here to approve right now.</p><button type="button" onClick={() => setTab("inbox")}>Back to your inbox</button></div>}
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
