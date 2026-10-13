import { useMemo, useRef, useSyncExternalStore } from "react";
import { CAPTURE_URL, MAX_CAPTURE_LENGTH, isCapture, isDraft } from "./thought-types";
import type { Capture, Draft } from "./thought-types";

type Snapshot = {
  draft: Draft;
  pending: Draft | null;
  busy: boolean;
  locallySaved: boolean;
  message: string;
  error: string;
  lastCapture: Capture | null;
};
type Dependencies = {
  storage: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  request: typeof fetch;
  newId: () => string;
};
const blank = (): Draft => ({ text: "", client_id: "" });

function browserDependencies(): Dependencies {
  let storage: Storage | null = null;
  try { storage = window.localStorage; } catch { /* Browser policy can block local storage. */ }
  return { storage, request: (...args) => fetch(...args), newId: () => crypto.randomUUID() };
}

// The store is independently testable; persistence occurs before network I/O.
export function createThoughtCaptureStore(
  headers: () => Record<string, string>,
  organismId = "default",
  dependencies: Dependencies = browserDependencies(),
) {
  const key = `drift:thought-draft:v1:${encodeURIComponent(organismId)}`;
  let state: Snapshot = {
    draft: blank(), pending: null, busy: false, locallySaved: false,
    message: "", error: "", lastCapture: null,
  };
  try {
    const raw = dependencies.storage?.getItem(key);
    if (raw) {
      const saved: unknown = JSON.parse(raw);
      if (saved && typeof saved === "object") {
        const value = saved as { draft?: unknown; pending?: unknown };
        if (isDraft(value.draft) && (value.pending == null || isDraft(value.pending))) {
          state = { ...state, draft: value.draft, pending: value.pending ?? null, locallySaved: true };
        } else state.error = "The stored draft could not be read. It has not been removed.";
      }
    }
  } catch { state.error = "Local draft storage is unavailable. Keep this page open until you capture."; }
  const listeners = new Set<() => void>();
  const update = (change: Partial<Snapshot>, persist = false) => {
    state = { ...state, ...change };
    if (persist) {
      let locallySaved = false;
      try {
        if (dependencies.storage) {
          if (!state.draft.text && !state.pending) dependencies.storage.removeItem(key);
          else dependencies.storage.setItem(key, JSON.stringify({ draft: state.draft, pending: state.pending }));
          locallySaved = true;
        }
      } catch { /* Keep the in-memory draft usable when storage is full. */ }
      state = { ...state, locallySaved };
    }
    listeners.forEach(listener => listener());
  };
  const setText = (text: string) => {
    if (text === state.draft.text) return;
    update({ draft: { text, client_id: text ? dependencies.newId() : "" }, error: "", message: "" }, true);
  };
  const clearDraft = () => update({ draft: blank(), error: "", message: "Local draft cleared. Saved thoughts are unchanged." }, true);
  const capture = async (): Promise<Capture | null> => {
    if (state.busy) return null;
    const sent = state.pending ?? state.draft;
    if (!sent.text.trim()) return null;
    let length = 0;
    for (const _character of sent.text) {
      if (++length > MAX_CAPTURE_LENGTH) {
        update({ error: "Drift accepts up to 1,000,000 characters per thought. Your full draft is still here; nothing was shortened or split." });
        return null;
      }
    }
    update({ busy: true, pending: sent, error: "", message: "Saving in Drift… You can keep typing." }, true);
    try {
      const response = await dependencies.request(CAPTURE_URL, {
        method: "POST", headers: { ...headers(), "Content-Type": "application/json" },
        body: JSON.stringify({ text: sent.text, client_id: sent.client_id }),
      });
      if (!response.ok) {
        if (response.status === 413 || response.status === 422) {
          throw new Error("Drift could not accept this thought. The limit is 1,000,000 characters; your full original and retry key are kept.");
        }
        if (response.status === 401 || response.status === 403) {
          throw new Error("Drift needs your session token. Your thought and retry key are kept; sign in and retry.");
        }
        throw new Error("Drift could not confirm the save. Your thought and retry key are kept; retry when ready.");
      }
      const result: unknown = await response.json();
      const saved = result && typeof result === "object" ? (result as { capture?: unknown }).capture : null;
      if (!isCapture(saved) || saved.text !== sent.text) {
        throw new Error("Drift returned an unexpected save response. Your full thought and retry key are kept.");
      }
      // Both identity and text must still match: a newer draft must never be cleared.
      const unchanged = state.draft.client_id === sent.client_id && state.draft.text === sent.text;
      update({ draft: unchanged ? blank() : state.draft, pending: null,
        lastCapture: saved, message: "Saved in Drift. Capturing is separate from processing." }, true);
      return saved;
    } catch (error) {
      update({ message: "", error: error instanceof TypeError
        ? "Cannot reach Drift. Your thought and retry key are kept; retry when you are connected."
        : error instanceof Error ? error.message : "Save not confirmed. Your thought and retry key are kept." });
      return null;
    } finally { update({ busy: false }); }
  };
  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    setText, clearDraft, capture,
  };
}

export function useThoughtCapture(headers: () => Record<string, string>, organismId = "default") {
  const currentHeaders = useRef(headers);
  currentHeaders.current = headers;
  const store = useMemo(() => createThoughtCaptureStore(() => currentHeaders.current(), organismId), [organismId]);
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  return { ...snapshot, setText: store.setText, clearDraft: store.clearDraft, capture: store.capture };
}
