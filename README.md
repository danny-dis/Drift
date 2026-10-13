# Drift

[![CI](https://github.com/danny-dis/Drift/actions/workflows/ci.yml/badge.svg)](https://github.com/danny-dis/Drift/actions/workflows/ci.yml)

Version **0.2.1** — [release notes](docs/releases/0.2.1.md).

A small thinking workspace on your computer. Write a messy thought, save it, and return to it later. Optional AI can suggest a summary, questions and project connections. Your original stays unchanged. Drift is not an autonomous coding factory.

## Install and start

Install **Python 3.12 or 3.13** first. Check with `python --version`; on Windows, `py -3.12` can replace `python` in the commands below.

```bash
python -m pip install "https://github.com/danny-dis/Drift/releases/download/v0.2.1/drift-0.2.1-py3-none-any.whl"
python -m drift.main --box ./drift_box --name Drift
```

Open **http://localhost:47116** in your browser. Keep the terminal open while using Drift. Press Ctrl+C in that terminal to stop it.

The wheel includes the dashboard: **Node.js is not needed to use this release.** Python package dependencies are downloaded during installation. You do not need an AI account or gateway to start saving and searching thoughts.

`./drift_box` is the folder holding your saved work, relative to the terminal's current directory. The Getting started guide shows its full location. Keep that folder when upgrading; start the new version with the same `--box` path. Unsaved browser drafts are not a replacement for saving into that folder.

To use a different port, add `--port 47117` and open that port instead. `DRIFT_HOST`, `DRIFT_PORT`, `DRIFT_BOX`, and `DRIFT_NAME` also set startup options. Existing `*_box` folders are discovered only when no explicit box is selected.

## Your first thought

1. Open **Inbox**, write anything, then click **Save**. No category is required. Ctrl/Cmd+Enter also saves.
2. **Saved** means the exact original is in Drift. AI processing is separate; a save does not mean AI has finished.
3. Open a saved thought to see its full original and, when available, separate suggestions and a report. Suggestions are unverified, not facts or replacements for your words.

The draft survives ordinary reloads. A failed save keeps the thought and its retry identity so retrying does not create another original. If browser storage is blocked or full, Drift says so: keep the page open until saving succeeds. Saved history supports search and pages. [Capture behavior and limits](docs/thought-capture.md).

## Optional AI

Open **Getting started** and choose **Check AI connection**. Opening the app or guide does not call a model. The explicit check consumes one permitted model call and uses no tools.

The default configuration expects a separately running DMR-X gateway at `http://127.0.0.1:47113/v1`, using `auto-free`. **Drift does not install, start or configure DMR-X.** Without it, you can still save and search; the check reports AI unavailable rather than pretending it is ready. A successful check records a real reply at that time, not a guarantee that later calls will succeed.

Free-only mode refuses ordinary paid-provider routes and disables paid embeddings, model-based memory scoring and remote decisions. There is **no silent paid fallback**. Settings live in `config.yaml` when running from source, or the installed package's bundled defaults. `DRIFT_PROVIDER`, `DRIFT_BASE_URL`, and `DRIFT_MODEL` override provider settings; credentials belong in their environment variables, never committed files.

Saving is local to the machine running Drift. **AI processing may send thought content through the gateway to a remote provider.** Recognized credentials are filtered for inference; filtering is not a guarantee that arbitrary private data is removed. Do not enter anything you would not want the configured provider to receive.

When an inference call fails, your original remains safe and work waits for explicit review. Restore the connection, inspect **Approvals**, and approve the same blocked task to retry. Model-call and context limits stay enforced. Tasks are not duplicated to bypass a block. Context that cannot safely retain a complete thought part is also stopped for review rather than silently losing its tail.

## Connection settings

Usually no token is needed on your local installation. **Connection settings** stays collapsed until you open it or the server asks for authentication. If the owner configured `DRIFT_API_TOKEN`, enter that Drift API token and click **Save token**. Status and history refresh immediately; your draft is not cleared.

The field uses `sessionStorage` when available and sends an Authorization header. If storage is blocked, it clearly warns that the token is held only until this page reloads; backend saving can still work. **Never enter a provider secret there.** Keep the service local; do not expose it to the public internet.

## Other sections

- **Office:** an illustrative high-DPI 2D workspace reflecting backend activity, not evidence of invisible workers. Animation is opt-in and respects reduced motion. [Office graphics](docs/office-scene.md).
- **Projects:** register a repository and optional local path; only registered repositories are inspected. Review advisory briefings and explicitly publish the managed `drift.md` section. Human content is preserved; Drift does not silently modify source code.
- **Research:** give a query and optional public URLs. Inspect retained sources, citations and reports. Missing/invalid evidence becomes `needs_review`; citation integrity is not independent fact checking. Repair resumes the same task.
- **Attention:** tasks, actual persisted call allowances, receipts and recorded decisions. Free calls still consume call allowance. Receipt cost fields are estimates unless a provider returns actual cost; a route name is not a billing receipt.
- **Approvals:** review blocked work before retrying. Marking a proposal implemented records a decision; it does not launch a coding agent.
- **Status:** technical runtime information. Tabs support arrows, Home and End, with normal Tab navigation into content.

`/api/ui/usage` now reads the real per-box call ledger. Its call total is for the current ISO week; recorded failures and known receipt-cost estimates have lifetime scopes. Untracked success/provider/capability breakdowns are unavailable, not fabricated zeros. Corrupt call accounting fails closed for inference while saving remains separate.

## Safety and limits

**Shell execution is disabled unless explicitly enabled** with `shell_enabled: true`. Opting in is not an OS sandbox; use a container/VM for isolation. Generated files stay in the organism's box. Fetched pages, model output and repository contents are untrusted data, not permission to change files, enable tools or spend money.

The backend binds to `127.0.0.1` by default. HTTP/WebSocket boundaries reject foreign browser origins; a CORS allowlist is not authentication. Public URL fetching refuses private/reserved addresses and URL credentials, validates redirects, pins the connected IP, and limits body size/time. Backup restoration rejects escaping paths and unsafe archive members.

Calls, output, context, tools, cycles and retries are bounded. External providers can have outages and rate limits. Optional remote decision adapters are disabled by default and are not necessary to use Drift. Long unattended usefulness and semantic accuracy cannot be guaranteed by a test suite.

## Development

Source builds require Python 3.12+, Node 20+ and npm:

```bash
python -m pip install -e '.[test]'
cd frontend && npm ci && npm test && npm run build && cd ..
python -m pytest tests -q -p no:cacheprovider
python -m drift.main --box ./drift_box --name Drift
```

`npm run build` explicitly selects production React even if the parent shell exports `NODE_ENV=development`. CI builds the locked frontend before Python tests so executable UI regressions are actually exercised. Fixture tests do not certify live inference; release acceptance separately tests a clean installed wheel, real gateway replies and browser/restart journeys.

For hot reload, start the backend and run `cd frontend && npm run dev`. Vite uses port 5173 and proxies to 47116. If needed, set `DRIFT_ALLOWED_ORIGINS=http://localhost:5173`; keep authentication separate from origin policy.
