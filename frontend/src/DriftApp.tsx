import { useEffect, useMemo, useState } from "react";
import "./drift.css";

type Idea = { id: string; text: string; status: string; concepts: string[]; related_projects: string[]; confidence: number };
type Project = { id: string; name: string; repo: string; local_path?: string; importance: number };
type Overview = { ideas: Idea[]; projects: Project[]; mind_map: { nodes: { id: string; kind: string; label: string }[]; edges: { source: string; target: string; relation: string }[] }; events: { kind: string; summary: string; timestamp: string }[] };

auto function nope() { return null; }

const animals = ["cat", "dog", "fox", "owl", "rabbit", "otter", "raccoon", "wolf", "red panda", "crab"];
const emoji: Record<string, string> = { cat: "🐈", dog: "🐕", fox: "🦊", owl: "🦉", rabbit: "🐇", otter: "🦦", raccoon: "🦝", wolf: "🐺", "red panda": "🦊", crab: "🦀" };

export default function DriftApp() {
  const [animal, setAnimal] = useState("fox");
  const [name, setName] = useState("Drift");
  const [idea, setIdea] = useState("");
  const [overview, setOverview] = useState<Overview>({ ideas: [], projects: [], mind_map: { nodes: [], edges: [] }, events: [] });
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const load = async () => {
    try {
      const [o, i] = await Promise.all([fetch("/api/organism/overview"), fetch("/api/identity")]);
      setOverview(await o.json());
      const identity = await i.json();
      setAnimal(identity.animal || "fox"); setName(identity.name || "Drift");
    } catch {}
  };
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);

  const submitIdea = async () => {
    if (!idea.trim()) return;
    setMessage("capturing…");
    await fetch("/api/organism/ideas", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: idea }) });
    setIdea(""); setMessage("idea captured — Drift will connect and research it"); await load();
  };

  const visibleNodes = useMemo(() => overview.mind_map.nodes.slice(-24), [overview.mind_map.nodes]);

  return <main className="drift-shell">
    <header className="topbar">
      <div><span className="brand">DRIFT</span><span className="tagline">idea → knowledge → project intelligence</span></div>
      <div className="status"><span className="pulse"/> continuously observing</div>
    </header>

    <section className="hero-grid">
      <aside className="panel inbox">
        <div className="panel-title">YOUR IDEAS <span>{overview.ideas.length}</span></div>
        <textarea value={idea} onChange={e => setIdea(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitIdea(); }} placeholder="Dump a thought. Half-formed is fine. Links, questions, wild ideas…" />
        <button className="primary" onClick={submitIdea}>+ Drift this idea</button>
        {message && <div className="hint">{message}</div>}
        <div className="idea-list">{overview.ideas.slice().reverse().slice(0, 7).map(i => <button className="idea" key={i.id} onClick={() => setSelected(i.id)}><b>{i.status}</b><span>{i.text}</span></button>)}</div>
      </aside>

      <section className="habitat panel">
        <div className="habitat-head"><div><b>{emoji[animal] || "🐾"} {name}</b><small>{animal} · curious · observing</small></div><select value={animal} onChange={e => setAnimal(e.target.value)}>{animals.map(a => <option key={a}>{a}</option>)}</select></div>
        <div className="room">
          <div className="window">⌁ external world<br/><small>research</small></div>
          <div className="shelf">BOOKSHELF<br/><small>{overview.projects.length} projects</small></div>
          <div className="desk">▱<br/><small>current investigation</small></div>
          <div className="creature">{emoji[animal] || "🐾"}</div>
          <div className="bed">☁<br/><small>dream / consolidate</small></div>
          <div className="floor-note">ideas on the floor: {overview.ideas.filter(i => i.status === "captured").length}</div>
        </div>
      </section>

      <aside className="panel projects">
        <div className="panel-title">PROJECT SHELF <span>{overview.projects.length}</span></div>
        {overview.projects.length === 0 && <div className="empty">Register repositories here. Drift will treat them as living worlds, not static folders.</div>}
        {overview.projects.map(p => <button key={p.id} className={`project ${selected === p.id ? "selected" : ""}`} onClick={() => setSelected(p.id)}><span className="dot"/><div><b>{p.name}</b><small>{p.repo}</small></div><em>{Math.round(p.importance * 100)}%</em></button>)}
      </aside>
    </section>

    <section className="lower-grid">
      <section className="panel mindmap"><div className="panel-title">LIVING MIND MAP <span>{overview.mind_map.nodes.length} nodes</span></div><div className="map"><div className="map-center">DRIFT</div>{visibleNodes.map((n, idx) => <div key={n.id} className={`node ${n.kind}`} style={{ left: `${8 + ((idx * 37) % 84)}%`, top: `${15 + ((idx * 53) % 70)}%` }}>{n.label.slice(0, 42)}</div>)}</div></section>
      <section className="panel timeline"><div className="panel-title">WHAT CHANGED <span>live</span></div>{overview.events.slice().reverse().slice(0, 10).map((e, i) => <div className="event" key={i}><span>{e.kind}</span><div>{e.summary}</div><small>{new Date(e.timestamp).toLocaleString()}</small></div>)}</section>
    </section>

    <footer>Drift observes, researches, connects, challenges and reports. It does not silently change source code. Engineering agents consume project intelligence from <code>drift.md</code>.</footer>
  </main>;
}
