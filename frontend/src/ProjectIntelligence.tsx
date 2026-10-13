import { useState } from "react";

type Props = {
  projectId: string;
  value?: Record<string, unknown>;
  headers: () => Record<string, string>;
  publishAvailable: boolean;
};

export default function ProjectIntelligence({ projectId, value, headers, publishAvailable }: Props) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  if (!value) return <p>No internal project briefing yet. New findings will appear here without editing source files.</p>;
  const publish = async () => {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/ui/projects/${encodeURIComponent(projectId)}/intelligence/publish`, {
        method: "POST", headers: headers(), body: JSON.stringify({ confirm: true }),
      });
      if (!response.ok) throw new Error(`Briefing was not published (${response.status}).`);
      setMessage("Published the advisory briefing to drift.md. Human-authored content was preserved; source code was not changed.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not confirm publication."); }
    finally { setBusy(false); }
  };
  return <section aria-label="Project intelligence">
    <h3>Current project briefing</h3>
    <p>Unverified advisory findings. Review the evidence before acting.</p>
    <p>{String(value.summary || "")}</p>
    {["findings", "challenges", "alternatives", "questions"].map(section => {
      const items = value[section];
      return Array.isArray(items) && items.length > 0 ? <div key={section}>
        <h4>{section.charAt(0).toUpperCase() + section.slice(1)}</h4>
        <ul>{items.filter((item): item is string => typeof item === "string").map((item, index) => <li key={index}>{item}</li>)}</ul>
      </div> : null;
    })}
    <p>This briefing stays inside Drift until you publish it.</p>
    {publishAvailable && <button onClick={() => { void publish(); }} disabled={busy}>Publish briefing to drift.md</button>}
    <p role="status" aria-live="polite">{message}</p>
  </section>;
}
