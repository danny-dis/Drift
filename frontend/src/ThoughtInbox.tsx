import { useCallback, useEffect, useId, useRef, useState } from "react";
import { CAPTURE_URL, STATUS_COPY, isCapture } from "./thought-types";
import type { CapturePage } from "./thought-types";
import { useThoughtCapture } from "./useThoughtCapture";
import "./thoughts.css";
import ThoughtInsights from "./ThoughtInsights";

type Props = {
  headers: () => Record<string, string>;
  onCaptured: () => void;
  organismId?: string;
};
const LIMIT = 20;

function useCaptureHistory(headers: Props["headers"], organismId: string) {
  const currentHeaders = useRef(headers);
  currentHeaders.current = headers;
  const [filter, setFilter] = useState({ q: "", offset: 0 });
  const [page, setPage] = useState<CapturePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    const requestId = ++sequence.current;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${CAPTURE_URL}?q=${encodeURIComponent(filter.q)}&limit=${LIMIT}&offset=${filter.offset}`,
        { headers: currentHeaders.current(), signal: request.signal },
      );
      if (!response.ok) {
        throw new Error(response.status === 401 || response.status === 403
          ? "Sign in with your session token to read saved thoughts. Your local draft is unchanged."
          : "Saved thoughts could not be loaded. Your local draft is unchanged.");
      }
      const value: unknown = await response.json();
      const result = value as CapturePage | null;
      if (!result || !Array.isArray(result.captures) || !result.captures.every(isCapture)
        || !Number.isSafeInteger(result.total) || result.total < 0
        || typeof result.has_more !== "boolean") {
        throw new Error("Drift returned an unreadable history response. Your local draft is unchanged.");
      }
      if (requestId === sequence.current) setPage(result);
    } catch (failure) {
      if (requestId !== sequence.current || request.signal.aborted) return;
      setError(failure instanceof TypeError ? "Cannot reach Drift. Retry when you are connected."
        : failure instanceof Error ? failure.message : "Saved thoughts could not be loaded.");
    } finally {
      if (requestId === sequence.current) setLoading(false);
    }
  }, [filter.q, filter.offset, organismId]);

  useEffect(() => {
    setPage(null);
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15_000);
    return () => {
      window.clearInterval(timer);
      ++sequence.current;
      controller.current?.abort();
    };
  }, [refresh]);

  return { page, loading, error, filter, setFilter, refresh };
}

function readableDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function ThoughtInbox({ headers, onCaptured, organismId = "default" }: Props) {
  const capture = useThoughtCapture(headers, organismId);
  const history = useCaptureHistory(headers, organismId);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const id = useId();
  const save = async () => {
    const result = await capture.capture();
    if (result) {
      void history.refresh();
      onCaptured();
    }
  };
  const earlierPending = capture.pending && capture.pending.client_id !== capture.draft.client_id;

  return (
    <section className="thought-inbox" aria-labelledby={`${id}-title`}>
      <header className="thought-heading">
        <h2 id={`${id}-title`}>Thought inbox</h2>
        <p>Write it as it comes. Save now; Drift organizes it separately in the background.</p>
      </header>
      <form className="thought-composer" onSubmit={event => { event.preventDefault(); void save(); }}>
        <label htmlFor={`${id}-draft`}>Capture a thought</label>
        <textarea id={`${id}-draft`} rows={7} value={capture.draft.text}
          aria-describedby={`${id}-hint ${id}-local`}
          onChange={event => capture.setText(event.target.value)}
          onKeyDown={event => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              void save();
            }
          }} />
        <p id={`${id}-hint`} className="thought-muted">Ctrl/Cmd + Enter to save. You can keep typing while saving.</p>
        <p id={`${id}-local`} className="thought-muted" aria-live="polite">
          {capture.locallySaved ? "Saved locally" : "Not saved locally — keep this page open until saved in Drift."}
        </p>
        {earlierPending && capture.pending && (
          <details className="thought-pending">
            <summary>Earlier thought awaiting save — Save retries this original first</summary>
            <pre className="thought-original" tabIndex={0} aria-label="Earlier original thought">{capture.pending.text}</pre>
            <p>Your newer draft stays here while the earlier thought is saved.</p>
          </details>
        )}
        <div className="thought-actions">
          <button type="submit" disabled={capture.busy || !(capture.pending?.text ?? capture.draft.text).trim()}>Save</button>
          <button type="button" className="thought-secondary"
            disabled={capture.busy || !!capture.pending || !capture.draft.text}
            onClick={capture.clearDraft}>Clear draft</button>
        </div>
        <div className="thought-feedback" aria-live="polite" aria-atomic="true">
          {capture.message && <p>{capture.message}</p>}
          {capture.error && <p className="thought-error" role="alert">{capture.error}</p>}
        </div>
      </form>

      <section className="thought-history" aria-labelledby={`${id}-history`}>
        <div className="thought-history-heading">
          <h3 id={`${id}-history`}>Saved thoughts</h3>
          <button type="button" className="thought-secondary" disabled={history.loading}
            onClick={() => { void history.refresh(); }}>Refresh</button>
        </div>
        <form className="thought-search" onSubmit={event => {
          event.preventDefault();
          history.setFilter({ q: search.trim(), offset: 0 });
        }}>
          <label htmlFor={`${id}-search`}>Search original thoughts</label>
          <div className="thought-search-controls">
            <input id={`${id}-search`} type="search" value={search}
              onChange={event => setSearch(event.target.value)} />
            <button type="submit">Search</button>
          </div>
        </form>
        <div aria-live="polite" className="thought-feedback">
          {history.loading && <p>Loading saved thoughts…</p>}
          {history.error && <p className="thought-error" role="alert">{history.error}</p>}
          {history.error && history.page && <p>Showing the last loaded results.</p>}
          {!history.loading && !history.error && history.page?.captures.length === 0 && (
            <p>{history.filter.q ? "No saved thoughts match this search." : "No saved thoughts yet. Your first one can start above."}</p>
          )}
        </div>
        {history.page && (
          <>
            <p className="thought-muted">{history.page.total} saved thoughts{history.filter.q ? " matching this search" : ""}</p>
            <ul className="thought-list" aria-busy={history.loading}>
              {history.page.captures.map(item => (
                <li key={item.id}>
                  <details open={selectedId === item.id} onToggle={event => {
                    const open = event.currentTarget.open;
                    setSelectedId(current => open ? item.id : current === item.id ? null : current);
                  }}>
                    <summary>
                      <span className="thought-summary-line">
                        <time dateTime={item.created_at}>{readableDate(item.created_at)}</time>
                        <span className={`thought-status${item.status === "needs_review" ? " thought-needs-review" : ""}`}>{STATUS_COPY[item.status].label}</span>
                      </span>
                      <span className="thought-preview">{item.text}</span>
                    </summary>
                    <div className="thought-detail">
                      <p>{STATUS_COPY[item.status].explanation}</p>
                      <h4>Full original thought</h4>
                      <pre className="thought-original" tabIndex={0} aria-label="Full original thought">{item.text}</pre>
                      {selectedId === item.id && <ThoughtInsights captureId={item.id} status={item.status} headers={headers} />}
                      {(item.idea_id || item.task_id || item.report_path) && <details>
                        <summary>Processing details</summary>
                        {item.idea_id && <p>Idea: <code>{item.idea_id}</code></p>}
                        {item.task_id && <p>Task: <code>{item.task_id}</code></p>}
                        {item.report_path && <p>Report: <code>{item.report_path}</code></p>}
                      </details>}
                    </div>
                  </details>
                </li>
              ))}
            </ul>
            <nav className="thought-pagination" aria-label="Saved thoughts pages">
              <button type="button" className="thought-secondary"
                disabled={history.loading || !!history.error || history.filter.offset === 0}
                onClick={() => history.setFilter(current => ({ ...current, offset: Math.max(0, current.offset - LIMIT) }))}>Previous</button>
              <span>{history.page.captures.length ? `${history.filter.offset + 1}–${history.filter.offset + history.page.captures.length}` : "0"} of {history.page.total}</span>
              <button type="button" className="thought-secondary"
                disabled={history.loading || !!history.error || !history.page.has_more}
                onClick={() => history.setFilter(current => ({ ...current, offset: current.offset + LIMIT }))}>Next</button>
            </nav>
          </>
        )}
      </section>
    </section>
  );
}
