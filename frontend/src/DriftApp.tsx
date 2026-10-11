import { useCallback, useEffect, useMemo, useState } from "react";
import "./drift.css";

// Blast radius: imported only by main.tsx. No backend symbols touched.
// Talks to backend only via /api/* fetch. No direct host access.

type Idea = { id: string; text: string; status: string; concepts?: string[]; related_projects?: string[]; confidence?: number };
type Project = { id: string; name: string; repo: string; local_path?: string; importance?: number; last_seen_commit?: string; last_round?: string };
type Status = { state?: string; thought_count?: number; memory_count?: number; model?: string; name?: string; animal?: string; focus_mode?: boolean; [k: string]: unknown };
type EvidenceItem = { summary: string; evidence: { url?: string; title?: string; quote?: string }[]; confidence: number; source: string; timestamp: string };
type Candidate = { source: string; description: string; project_id: string; base_priority: number; estimated_cost: number };
type Receipt = { task_id: string; estimated_tokens: number; estimated_cost: number; model_provider: string; timestamp: string; context_budget?: number };
type Approval = { id: string; goal: string; objective?: string; project_id?: string; blockers?: string[]; phase?: string };
type Session = { id: string; query: string; state: string; phase?: string; next_action?: string; rev?: number; repairs?: number; project_id?: string; errors?: string[]; query_history?: unknown[]; notes?: unknown[]; tools?: unknown[]; scripts?: unknown[]; file_changes?: unknown[]; report_attempts?: unknown[]; repair_context?: unknown[]; sources?: {id: string; url: string; excerpt: string}[]; report?: {findings?: string[]; citations?: {source_id: string; quote?: string}[]} | null };
type Decisions = { loop: Record<string, unknown>; memory: Record<string, unknown> };
type Task = {id: string; goal: string; status: string; phase: string; last_evidence?: string; blockers?: string[]};

type Tab = "status" | "inbox" | "projects" | "research" | "attention" | "approvals";
const TABS: { id: Tab; label: string }[] = [
  { id: "status", label: "Status" },
  { id: "inbox", label: "Inbox" },
  { id: "projects", label: "Projects" },
  { id: "research", label: "Research" },
  { id: "attention", label: "Attention" },
  { id: "approvals", label: "Approvals" },
];

function authHeaders(): Record<string, string> {
  const t = sessionStorage.getItem("drift_token") || "";
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

function isHttp(url: string): boolean {
  return url.startsWith("https://") || url.startsWith("http://");
}

export default function DriftApp() {
  const [tab, setTab] = useState<Tab>("status");
  const [token, setToken] = useState(() => sessionStorage.getItem("drift_token") || "");
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
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [receiptTotal, setReceiptTotal] = useState<number | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionDetail, setSessionDetail] = useState<Session | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskReport, setTaskReport] = useState("");
  const [sessionsNote, setSessionsNote] = useState("");
  const [selected, setSelected] = useState<{ kind: string; id: string; label: string; detail: string } | null>(null);
  const [projectDetail, setProjectDetail] = useState<{ events: { summary: string }[]; ideas: Idea[]; drift_md: string } | null>(null);

  // forms (inputs preserved on failed capture)
  const [ideaText, setIdeaText] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [reg, setReg] = useState({ name: "", repo: "", local_path: "", importance: "0.5" });
  const [regNote, setRegNote] = useState("");
  const [sessQ, setSessQ] = useState("");
  const [sessUrls, setSessUrls] = useState("");
  const [sessProj, setSessProj] = useState("");

  const saveToken = () => { sessionStorage.setItem("drift_token", token); setMsg("token saved locally (session only)"); };

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status", { headers: authHeaders() });
      if (!res.ok) { setStatusErr(`status ${res.status}`); return; }
      setStatus(await res.json()); setStatusErr("");
    } catch (e) { setStatusErr(String(e)); } finally { setStatusLoading(false); }
  }, []);

  const loadAll = useCallback(async () => {
    const get = async (url: string) => {
      try {
        const res = await fetch(url, { headers: authHeaders() });
        if (!res.ok) return null; // do not pretend unavailable fields work
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
    if (cd) setCandidates(cd.candidates || []);
    if (rc) { setReceipts(rc.receipts || []); setReceiptTotal(rc.total_estimated_cost ?? null); }
    if (ap) setApprovals(ap.pending || []);
    if (ss && ss.sessions) { setSessions(ss.sessions); setSessionsNote(""); }
    else setSessionsNote("Research sessions unavailable; check backend/authentication");
  }, []);

  useEffect(() => { loadStatus(); loadAll(); }, [loadStatus, loadAll]);
  useEffect(() => { const t = setInterval(loadAll, 15000); return () => clearInterval(t); }, [loadAll]);
  useEffect(() => { const t = setInterval(loadStatus, 10000); return () => clearInterval(t); }, [loadStatus]);

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
    setSelected({ kind: "project", id: p.id, label: p.name, detail: `${p.repo}${p.local_path ? ` · ${p.local_path}` : ""}` });
    try {
      const res = await fetch(`/api/ui/projects/${p.id}`, { headers: authHeaders() });
      if (!res.ok) { setProjectDetail(null); return; }
      const d = await res.json();
      setProjectDetail({ events: d.events || [], ideas: d.ideas || [], drift_md: d.drift_md || "" });
    } catch { setProjectDetail(null); }
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

  return (
    <main className="drift-shell">
      <header className="topbar">
        <div><span className="brand">DRIFT</span><span className="tagline">local thinking workspace · bounded and evidence-linked</span></div>
        <div className="status" aria-live="polite">
          {statusLoading ? "loading status…" : statusErr ? `status error: ${statusErr}` : status ? `${status.state || "unknown"} · thoughts ${status.thought_count ?? "?"} · mem ${status.memory_count ?? "?"} · ${String(status.model || "")}` : "status unavailable"}
        </div>
      </header>

      <section className="auth-row" aria-label="API authentication">
        <label htmlFor="drift-token">Auth token (optional, session only):</label>
        <input id="drift-token" type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Bearer token" autoComplete="off" />
        <button onClick={saveToken}>Save token</button>
        <small>stored in sessionStorage, sent as Authorization header. Never enter provider secrets here.</small>
      </section>

      <nav className="tabs" role="tablist" aria-label="Drift sections">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "tab active" : "tab"} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </nav>

      {msg && <div className="hint" role="status">{msg}</div>}
      {err && <div className="error" role="alert">{err}</div>}

      {tab === "status" && (
        <section role="tabpanel" aria-label="Status" className="panel">
          <div className="panel-title">LIVE STATUS <span>{identity.name || "Drift"} {identity.animal ? `· ${identity.animal}` : ""}</span></div>
          <div className="pad">
            {statusLoading && <p>Loading live status…</p>}
            {statusErr && <p role="alert">Could not reach /api/status: {statusErr}. Backend may be down; no fields are faked.</p>}
            {status && (
              <ul>
                <li>state: {String(status.state ?? "unknown")}</li>
                <li>thoughts: {String(status.thought_count ?? "n/a")}</li>
                <li>memories: {String(status.memory_count ?? "n/a")}</li>
                <li>model/route: {String(status.model ?? "n/a")} (free route; no paid inference from UI)</li>
                <li>focus mode: {String(status.focus_mode ?? "n/a")}</li>
              </ul>
            )}
            <p><small>Shell default disabled; registered paths only; local-only. Polls /api/status every 10s. Missing fields shown as n/a, never invented.</small></p>
          </div>
        </section>
      )}

      {tab === "inbox" && (
        <section role="tabpanel" aria-label="Inbox" className="panel">
          <div className="panel-title">INBOX <span>{ideas.length} ideas</span></div>
          <div className="pad">
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
          </div>
        </section>
      )}

      {tab === "projects" && (
        <section role="tabpanel" aria-label="Projects" className="panel">
          <div className="panel-title">PROJECT REGISTER + SHELF <span>{projects.length}</span></div>
          <div className="pad">
            <form onSubmit={e => { e.preventDefault(); registerProject(); }}>
              <label htmlFor="reg-name">Name</label>
              <input id="reg-name" value={reg.name} onChange={e => setReg({ ...reg, name: e.target.value })} required />
              <label htmlFor="reg-repo">Repo</label>
              <input id="reg-repo" value={reg.repo} onChange={e => setReg({ ...reg, repo: e.target.value })} placeholder="org/repo" required />
              <label htmlFor="reg-path">Local path (optional, must be registered)</label>
              <input id="reg-path" value={reg.local_path} onChange={e => setReg({ ...reg, local_path: e.target.value })} />
              <label htmlFor="reg-imp">Importance (0-1)</label>
              <input id="reg-imp" value={reg.importance} onChange={e => setReg({ ...reg, importance: e.target.value })} inputMode="decimal" />
              <button className="primary" type="submit">Register project</button>
            </form>
            {regNote && <p role="status">{regNote}</p>}
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
                {projectDetail ? (
                  <>
                    <p>Related ideas: {projectDetail.ideas.length} · events: {projectDetail.events.length}</p>
                    <ul>{projectDetail.ideas.slice(0, 5).map(i => <li key={i.id}>{i.text}</li>)}</ul>
                    {projectDetail.drift_md ? <pre>{projectDetail.drift_md.slice(0, 2000)}</pre> : <p><small>No drift.md summary available.</small></p>}
                  </>
                ) : <p><small>Detail unavailable (backend returned no detail).</small></p>}
              </div>
            )}
            <div className="map" aria-label="Deterministic mind map">
              <div className="map-center">DRIFT</div>
              {nodes.map((n, idx) => <button key={n.id} className={`node ${n.kind}`} style={pos(idx)} onClick={() => setSelected({ kind: n.kind, id: n.id, label: n.label, detail: n.kind === "project" ? "project node — open Projects detail above" : "idea node — see Inbox" })}>{n.label.slice(0, 42)}</button>)}
            </div>
            <p><small>Edges ({edges.length}, deterministic, no graph lib):</small></p>
            <ul>{edges.slice(0, 10).map((e, k) => <li key={k}><small>{e.source} —{e.relation}→ {e.target}</small></li>)}</ul>
          </div>
        </section>
      )}

      {tab === "research" && (
        <section role="tabpanel" aria-label="Research" className="panel">
          <div className="panel-title">EVIDENCE + RESEARCH SESSIONS</div>
          <div className="pad">
            <h3>Findings ({findings.length})</h3>
            <ul>{findings.slice(-10).map((f, k) => <li key={k}>{f.summary} <small>· confidence {f.confidence ?? "unverified"}</small></li>)}</ul>
            <h3>Evidence with citations (rendered safely)</h3>
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
            <h3>Research sessions {sessionsNote && <small>· {sessionsNote}</small>}</h3>
            <form onSubmit={e => { e.preventDefault(); createSession(); }}>
              <label htmlFor="sess-q">Query</label>
              <input id="sess-q" value={sessQ} onChange={e => setSessQ(e.target.value)} required />
              <label htmlFor="sess-urls">URLs (comma-separated, optional)</label>
              <input id="sess-urls" value={sessUrls} onChange={e => setSessUrls(e.target.value)} />
              <label htmlFor="sess-proj">Project id (optional)</label>
              <input id="sess-proj" value={sessProj} onChange={e => setSessProj(e.target.value)} />
              <button className="primary" type="submit">Start session</button>
            </form>
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
        <section role="tabpanel" aria-label="Attention and budget" className="panel">
          <div className="panel-title">TASK / ATTENTION + BUDGET + RECEIPTS</div>
          <div className="pad">
            <h3>Tasks</h3>
            <ul>{tasks.map(t => <li key={t.id}>{t.goal} · {t.status} / {t.phase} {t.last_evidence && <button onClick={() => openTaskReport(t.id)}>Read report</button>}{t.blockers?.length ? <small> · {t.blockers.join("; ")}</small> : null}</li>)}</ul>
            {taskReport && <pre>{taskReport}</pre>}
            <h3>Decision telemetry</h3>
            {decisions ? <>
              <p>Recorded loop and memory decisions; keyword gates are not semantic judgments. Unmeasured metrics remain unavailable.</p>
              <details open><summary>Loop decisions</summary><pre>{JSON.stringify(decisions.loop, null, 2)}</pre></details>
              <details><summary>Memory decision summary (no raw memory)</summary><pre>{JSON.stringify(decisions.memory, null, 2)}</pre></details>
            </> : <p>Decision telemetry unavailable; check backend/authentication.</p>}
            <h3>Budget</h3>
            {Object.keys(budget).length === 0 ? <p><small>No budget data (backend unavailable).</small></p> : (
              <ul>{Object.entries(budget).map(([k, v]) => <li key={k}>{k}: {String(v)}</li>)}</ul>
            )}
            <h3>Attention candidates (why each task matters)</h3>
            {candidates.length === 0 && <p><small>No candidates queued.</small></p>}
            <ul>
              {candidates.map((c, k) => (
                <li key={k}><b>{c.source}</b> — {c.description} <small>· project {c.project_id || "none"} · priority {c.base_priority} · cost {c.estimated_cost}</small></li>
              ))}
            </ul>
            <h3>Receipts {receiptTotal !== null && <small>· total {receiptTotal}</small>}</h3>
            <ul>{receipts.slice(-10).map((r, k) => <li key={k}><small>{r.task_id} · {r.estimated_tokens} tok · {r.estimated_cost} · {r.model_provider} · {r.timestamp}</small></li>)}</ul>
          </div>
        </section>
      )}

      {tab === "approvals" && (
        <section role="tabpanel" aria-label="Approvals" className="panel">
          <div className="panel-title">BLOCKED TASK APPROVALS <span>{approvals.length} pending</span></div>
          <div className="pad">
            {approvals.length === 0 && <p><small>Nothing blocked. Blocked tasks appear here for human approval.</small></p>}
            <ul>
              {approvals.map(a => (
                <li key={a.id}>
                  <p><b>{a.goal}</b> <small>· {a.phase || "blocked"} · project {a.project_id || "none"}</small></p>
                  {(a.blockers || []).length > 0 && <p><small>Blockers: {(a.blockers || []).join("; ")}</small></p>}
                  <button onClick={() => approve(a.id)}>Approve {a.id}</button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <footer><small>Local-only UI. Backend owns data; UI never touches host files. Generated reports require owner review. Sources and model output are untrusted.</small></footer>
    </main>
  );
}
