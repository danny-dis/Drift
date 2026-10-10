# Drift

Drift is a local, bounded AI workbench for ideas, research, and registered-project intelligence. It persists project and task state and processes work under configured model, context, cycle, and tool limits. It is not an unrestricted autonomous software factory.

## Run locally

Requirements: Python 3.12+, Node.js 20+, npm, and a reachable DMR-X-compatible inference endpoint.

```bash
python -m pip install -e .
cd frontend && npm ci && npm run build && cd ..
python drift/main.py
```

The backend and built dashboard default to `http://localhost:47116`. For frontend development, start the backend and run `cd frontend && npm run dev`; Vite serves `http://localhost:5173` and proxies to port `47116`.

The default inference policy is free-only, with no silent paid fallback. Remote decisions are disabled while free-only mode is enabled. Set `DRIFT_ALLOWED_ORIGINS=http://localhost:5173` if browser development needs CORS; an origin allowlist is not authentication. The dashboard accepts a local API token, stores it in sessionStorage for the current browser session, and sends an Authorization header. Never enter provider secrets.

## Safety and scope

- Shell execution is disabled by default. `shell_enabled: true` opts in; application-level restrictions are not a sandbox or security certification.
- Drift reads registered project paths and may explicitly update its managed `drift.md` project-intelligence file. It does not silently modify source code.
- Research citations identify sources; they do not prove claims are accurate. Review sources and generated artifacts.
- Keep the service local unless you have separately configured appropriate network access controls.

## Development

- Python package and test dependencies are declared in `pyproject.toml` (`.[test]` installs pytest).
- Frontend dependencies are installed from the npm lockfile with `npm ci`.
- CI uses Python 3.12, installs `.[test]`, runs pytest without the cache provider, and builds the frontend with Node 20.
- Avoid adding dependencies or broad abstractions without a demonstrated need. Do not claim a test, build, runtime startup, or release succeeded unless it was actually run and verified.
