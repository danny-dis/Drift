import { useEffect, useState } from "react";

type Insights = { summaries: string[]; questions: string[]; qualification: string | null; progress: { complete: number; total: number } };
type Props = { captureId: string; status: string; headers: () => Record<string, string> };

export default function ThoughtInsights({ captureId, status, headers }: Props) {
  const [value, setValue] = useState<Insights | null>(null);
  const [error, setError] = useState("");
  const [report, setReport] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    fetch(`/api/ui/captures/${encodeURIComponent(captureId)}/insights`, { headers: headers(), signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("Insights are unavailable; your saved original is unchanged.");
        const data = await response.json();
        if (!Array.isArray(data.summaries) || !Array.isArray(data.questions) || !data.progress) throw new Error("Unreadable insight response.");
        setValue(data);
      }).catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Could not load insights."); });
    return () => controller.abort();
  }, [captureId, status, headers]);
  const readReport = async () => {
    try {
      const response = await fetch(`/api/ui/captures/${encodeURIComponent(captureId)}/report`, { headers: headers() });
      if (!response.ok) throw new Error("No processing report is available yet.");
      const data = await response.json();
      setReport(String(data.text));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not load report."); }
  };
  return <section aria-label="Thought insights">
    <h4>What Drift made of this</h4>
    <p>These are unverified suggestions, not replacements for your original.</p>
    {error && <p role="alert">{error}</p>}
    {value && <>
      <p>{value.progress.total ? `${value.progress.complete} of ${value.progress.total} parts processed` : "Saved; processing has not started."}</p>
      <ul>{value.summaries.map((summary, index) => <li key={index}>{summary}</li>)}</ul>
      {value.qualification && <p>Suggested direction: {value.qualification.toLowerCase()}. You remain in control.</p>}
      {value.questions.length > 0 && <details><summary>Questions to return to</summary><ul>{value.questions.map((question, index) => <li key={index}>{question}</li>)}</ul></details>}
      {value.progress.complete > 0 && <button type="button" onClick={() => { void readReport(); }}>Read processing report</button>}
    </>}
    {report && <pre className="thought-original" tabIndex={0}>{report}</pre>}
  </section>;
}
