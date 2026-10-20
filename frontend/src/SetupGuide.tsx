export type SetupStatus = {
  version: string;
  capture_ready: boolean;
  storage_path: string;
  auth_required: boolean;
  free_only: boolean;
  shell_enabled: boolean;
  processing: {
    state: "unchecked" | "ready" | "unavailable" | "limited";
    message: string;
    model: string;
    checked_at: string | null;
  };
};

type Props = {
  setup: SetupStatus | null;
  error: string;
  checking: boolean;
  onCheck: () => void;
  onSuggestions: () => void;
};

export default function SetupGuide({ setup, error, checking, onCheck, onSuggestions }: Props) {
  const processing = setup?.processing;
  const aiLabel = processing?.state === "ready" ? "AI replied at last check"
    : processing?.state === "limited" ? "AI check limited"
    : processing?.state === "unavailable" ? "AI unavailable" : "AI not checked";
  return (
    <details className="setup-guide">
      <summary>Getting started <span className="setup-readiness" aria-live="polite">
        {setup ? setup.capture_ready ? "Saving ready" : "Saving unavailable" : "Saving not verified"}
        {" · "}{aiLabel}
      </span></summary>
      <ol className="setup-steps">
        <li><strong>Save a thought.</strong> Use the Inbox below. Saving does not need AI; a failed save keeps your draft.</li>
        <li><strong>Check optional AI.</strong> Only when you choose: this check uses one permitted model call from your workspace allowance. No tools or paid fallback.
          <button type="button" onClick={onCheck} disabled={checking} aria-describedby="setup-check-cost">{checking ? "Checking AI…" : "Check AI connection"}</button>
          <small id="setup-check-cost">Opening this guide and refreshing status do not call a model.</small>
        </li>
        <li><strong>View suggestions.</strong> Open a saved thought for its suggestions and reports when available, or <button type="button" onClick={onSuggestions}>View saved thoughts</button>. AI output needs your review.</li>
      </ol>
      <div className="setup-boundaries">
        {error && <p role="alert">{error}</p>}
        <details><summary>Storage, privacy & technical details</summary>
        {processing && <p role="status">{aiLabel}: {processing.message}
          {processing.model && <> Route: <code>{processing.model}</code>.</>}
          {processing.checked_at && <> Checked: <time dateTime={processing.checked_at}>{processing.checked_at}</time>. A real reply then does not guarantee the next call.</>}
        </p>}
        <p>Saved thoughts live in the backend box on the machine running Drift{setup ? <>: <code>{setup.storage_path}</code></> : " (storage location not yet available)"}. Unsaved drafts stay in this browser’s local storage, not in the box.</p>
        <p>Saving is local to that machine, not a promise of offline AI or private inference. AI processing may send thought content through the configured gateway to a remote provider. The token below is only for Drift’s API, never a provider key.</p>
        {setup && <p>Provider policy: {setup.free_only ? "free-only" : "configured provider policy"}; connection check never uses paid fallback. Shell: {setup.shell_enabled ? "enabled by configuration; restrictions are not a sandbox" : "disabled"}. {setup.auth_required ? "Drift API authentication required." : "Drift API token not required."}</p>}
        </details>
      </div>
    </details>
  );
}
