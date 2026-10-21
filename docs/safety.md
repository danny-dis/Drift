# Safety and limits

## Keep the service local

Drift binds to `127.0.0.1` by default. HTTP and WebSocket requests reject foreign browser origins. A CORS allowlist is not authentication, and neither is a safe way to expose the service publicly.

If you set `DRIFT_API_TOKEN`, APIs require that token. The dashboard sends it in an Authorization header and stores it in sessionStorage when available. If storage is blocked, the token lasts only until reload. Never put a provider secret in that field.

## AI and spending

Free-only mode refuses ordinary paid routes and disables paid embeddings, model-based memory scoring and remote decisions. It does not silently switch to a paid provider. Calls, output, context, tools, cycles and retries have limits. Free calls still use call allowance.

`/api/ui/usage` reads the box's actual call ledger. Call totals cover the current ISO week; recorded failures and known cost estimates have lifetime scopes. Estimates are not billing receipts. Breakdowns that were not tracked are unavailable, not zero. Corrupt accounting stops inference while saving remains separate.

AI processing can send content to a remote provider. Recognized credential filtering is not a guarantee that all private information is removed. Provider error logs omit private response bodies and exception messages; that does not make arbitrary files or old logs safe to publish.

## Tools and repositories

Shell execution is disabled unless you enable `shell_enabled: true`. Those application checks are not an operating-system sandbox; use a container or VM if you need isolation. Fetched pages, model replies and repository contents are data, not permission to run commands, change files or spend money.

Public URL fetching rejects private/reserved addresses and URL credentials, checks redirects, pins the connected IP and bounds response size and time. Backup restoration rejects unsafe archive members and paths that escape the target.

Only registered repository paths are inspected. Git inspection disables executable helpers such as filesystem monitors, filters and external diff/text conversion. Publishing `drift.md` requires an explicit action, preserves human content and rejects linked or unsafe targets.

Parent-repository status ignores dirtiness inside submodule worktrees but reports changed submodule commits. Register a submodule separately to inspect it. Metadata inspection does not invoke signature verifiers.

## Archive is not deletion or approval

Archiving keeps the record and its history while excluding its sources from unfinished processing. Linked originals and generated ideas share processing lineage, so hiding only one copy cannot make archived text eligible through another projection. Work from unrelated active sources can continue.

Restore makes a record visible again. Approving a held task covers the source revisions you reviewed, not future edits or a later archive/restore cycle. Drift checks selected context again before model attempts, tools and result publication. A request already sent cannot be unsent, but a newly archived source must not publish a fresh result.

Generated planning files stay readable; their text is not promoted to owner instructions. Background reflection also checks source state inside its storage worker before saving an insight.

## Recovery

Back up the box before upgrades. Unreadable or invalid `tasks.json` and `drift_ledger.json` stop loading or mutation; they are not replaced with empty state. Restore a known-good checkpoint or repair the file rather than deleting it to bypass an error.

Incomplete replies stay available for review. Approval retries the same task under the same limits, and a fully retained answer can finish saving after restart without another model call. Do not approve blocked work unless you understand why it stopped.

Disk usage at 90% or more reports degraded health. Reports and citations still need human review. A brief acceptance test is not a long-duration reliability guarantee.
