# Thought capture and the Drift workbench

Drift is a local-first idea and research workbench, not a clinical ADHD product. Its capture flow is designed for unfinished sentences, typo-heavy notes, rapid submissions, interruptions and long brain dumps. It does not require categories before saving and does not treat every thought as a task the owner must manage.

## Capture first

1. Open **Thoughts** and write or paste the thought as it is.
2. Save with the button or Ctrl/Cmd + Enter. Ordinary Enter creates a new line.
3. Keep typing while a save is in flight. A successful older save does not clear a newer draft.
4. If the save is not confirmed, the original submission and retry identity remain available. Save retries that original first; a newer draft stays separate.
5. Search saved history and open a thought to read its complete original. Generated summaries and questions appear separately.

The server commits each accepted original to `captures.sqlite3` before any model call. Reusing the same client submission ID with the same original is a retry, not a second capture. Two independent submissions with identical text remain two separate thoughts. There is no automatic deletion, text rewriting, or content-based deduplication.

The explicit limit is **1,000,000 Unicode characters per capture**. Oversized entries are rejected rather than truncated, and the browser retains the draft. Storage capacity is finite; save errors are shown rather than reported as success.

## Edit, archive and restore

Open a saved thought and choose **Edit thought** to change its current text. The original stays available in its details. Editing does not turn an old AI suggestion into a new answer. Revision conflicts ask you to reload rather than overwrite another edit.

**Archive thought** asks for confirmation, hides the thought from active lists and holds unfinished processing. You can include archived records in the list and restore them later. Restore makes the record visible; it does not approve its held tasks or recreate missing processing parts. Review **Needs approval** before allowing that work to continue.

## Local drafts and privacy

The browser retains the current draft and pending submission in localStorage when that storage is available. If browser policy, quota or a write failure prevents local saving, the UI warns the owner to keep the page open. Clearing a local draft does not delete saved server originals. Browser-local drafts are not a cross-device backup.

Original thoughts and generated reports are sensitive workspace data. The SQLite store is not encrypted by this feature. Restrict access to the workspace and browser profile, and keep backups. Recognizable credentials are redacted from model-bound text and transient diagnostics without changing the original. Redaction is not a guarantee that every possible secret format is detected.

Diagnostic API logs no longer persist whole thought contents in the shared process log. The inference provider is configured separately: a locally stored thought can still be sent to a remote model if that provider is selected. “Local-first” describes capture/storage, not a guarantee of fully local inference. Bind to loopback by default; configure authentication before exposing the API to other machines.

## Background organization and recovery

The background worker converts saved captures into bounded 1,200-character processing parts. The full original stays in the capture store; its chunk text is also retained in durable task checkpoints. Work creation is bounded per intake pass. Summaries are advisory and uncertainty remains visible.

A capture is marked processed only after all its expected parts have terminal completion checkpoints. An interruption between writing an outcome and writing the final task checkpoint can be resumed without asking the model again. Incomplete captures are reconciled after restart; save endpoints remain usable without a functioning model.

Complete answer artifacts are retained before finalization and reused after interruptions in rename, memory/outcome recording or intermediate task phases. A fully written temporary answer can be promoted after an interrupted rename; unfinished temporary files are not accepted as complete answers. Recovery runs before model-call admission, including when the call allowance is exhausted.

When the provider explicitly reports a token limit or another incomplete termination, Drift retains the partial text separately, prevents incomplete tool execution, and blocks the task for review. Approving the same task preserves its original and report metadata. The capture stays `needs_review` while any part remains blocked, otherwise returns to `queued`; restart reconciliation repairs an interrupted approval projection without another model call.

Processing may wait when the model is unavailable or the configured daily/weekly call allowance is exhausted. **Activity & budget** shows actual call counts, remaining allowance, wait reason and reset time separately from estimated money spent. Free inference still uses the call allowance.

## Ideas, projects and research

Task answers produce structured summaries, concepts, questions, challenges, alternatives and an advisory PROJECT / RESEARCH / PARKED suggestion. Parking is not deletion. A suggestion does not create a repository or authorize coding.

Related project intelligence is kept inside Drift by default. Writing the reviewed intelligence to a registered project's DRIFT.md requires an explicit owner action and a writable project path. Model findings are not automatically labeled verified.

Research retains readable fetched sources, exact citations and bounded review/repair state. Compressed pages are decoded with bounded gzip/deflate handling, declared charset support and explicit rejection of unsupported, malformed or over-expanding payloads. Existing network safety rules still apply.

## Verification and limits

Focused regressions cover exact originals, concurrent burst saves, distinct repeated thoughts, client-ID retries, long entries, pagination/search/reopening, checkpoint recovery, credential redaction, project publication and model failures. Browser acceptance separately exercises real keyboard/form interactions, interrupted saves and responsive layouts.

The [0.2.3 release checks](releases/0.2.3.md) also used a real Mercury 3 response to process a proposal, preserve its exact original and reopen the result after restart. Retrying the same saved capture did not spend another call. This is not a long-duration reliability test, clinical validation or a multi-device synchronization feature. Generated findings still need review.
