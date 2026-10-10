# Drift

A small, local-first thinking workspace: capture ideas, connect projects, research sources, review proposals, and retain useful context across restarts. Drift is not an autonomous coding factory.

## Run

Requires Python 3.12+, Node 20+ and a reachable DMR-X gateway. The checked-in configuration uses `http://127.0.0.1:47113/v1` and the `auto-free` route.

```bash
python -m pip install -e '.[test]'
cd frontend && npm ci && npm run build && cd ..
python -m drift.main --name drift
```

Open **http://localhost:47116**. Existing `*_box` folders are discovered. For a persistent box outside the checkout, use:

```bash
python -m drift.main --box /absolute/path/drift_box --name drift
```

Settings live in `config.yaml`. `DRIFT_HOST`, `DRIFT_PORT`, `DRIFT_BOX` and `DRIFT_NAME` override startup options. Use `DRIFT_PROVIDER` to override the provider. Supply provider credentials through the corresponding environment variable; never commit secrets.

The gateway is a separate service: Drift does not install, start or configure DMR-X. Free-only mode refuses ordinary paid-provider routes and disables paid embeddings, model-based memory scoring and remote decisions. There is no silent paid fallback. Receipt cost fields are estimates unless a provider returns actual cost; a route name alone is not a billing receipt.

## What the dashboard does

- **Capture:** stores the original idea immediately, with project connections. Work is queued separately; an API success does not mean model processing is finished.
- **Projects:** register a repository and optional local path; inspect project intelligence and explicitly update its managed `drift.md` file.
- **Research:** start a query with public source URLs and optional project association, inspect claims/citations, and review a persisted Markdown report. Sessions without valid evidence become `needs_review`, not verified.
- **Tasks/approvals:** inspect queued and blocked work; an explicit approval resumes a blocked task. Scheduling does not silently bypass a block.
- **Memory/status:** inspect events, decisions, budgets, receipts and a simple dependency-free mind map.

The browser calls the backend API, not DMR-X or the computer directly. The backend can read registered repositories and write the managed `drift.md`; it does not silently modify source code. Model-created files stay inside the organism's box. Model suggestions are not automatically implemented in a repository.

Completed owner questions are saved as unverified answer reports. Research citations must name retained sources, and quotation text must occur in the source. Citation validation is not independent fact-checking. Review the actual sources before relying on a claim. Proposal transitions retain provenance; marking a proposal implemented records a lifecycle decision, it does not run a coding agent.

## Safety and resource limits

**Shell execution is disabled unless explicitly enabled** with `shell_enabled: true`. Opting in is not a sandbox; use an OS container/VM if you need isolation. Fetched pages and model output are untrusted data, not authority to change permissions or spend money.

The service binds to `127.0.0.1` by default. HTTP and WebSocket mutation boundaries reject cross-origin browser requests. Set `DRIFT_API_TOKEN` to require a bearer token; the dashboard's token field stores it in `sessionStorage` for that browser session and sends an Authorization header. Never put a provider secret in that field. Do not expose Drift to the public internet.

Public URL fetching refuses local/private/reserved addresses and credential-bearing URLs, validates redirects, pins the connected IP and limits body size/time. No general shell or unrestricted repository write tool is exposed by default.

Calls, output, context, tool rounds, cycle duration and retry counts are bounded. Daily model-call accounting and attention budgets persist per box. Corrupt budget data fails closed. A failed provider call or exhausted task blocks work for explicit review rather than spinning forever. Optional remote decision adapters are disabled by default and are not required for operation; their network behavior needs separate verification before opt-in use.

## Development and tests

```bash
python -m pytest tests -q -p no:cacheprovider
cd frontend && npm run build && npx tsc --noEmit
```

Tests use local fixtures, not live inference. A real gateway/browser/restart journey is a separate acceptance check. CI installs Python test dependencies and builds the frontend using the npm lockfile.

For hot reload, start the backend and run `cd frontend && npm run dev`. Vite runs on port 5173 and proxies API/WebSocket requests to 47116. If needed, set `DRIFT_ALLOWED_ORIGINS=http://localhost:5173`; a CORS allowlist is not authentication.

Keep the implementation lean: one canonical store for each domain, local JSON/JSONL/SQLite state, existing Python/FastAPI and React/Vite stacks, no new orchestration framework. Architecture/research references live in `docs/` and are not a promise that every upstream system was cloned or every optional remote service was verified.
