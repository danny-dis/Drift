# Local continuous runtime

Run from the Drift checkout using its dependency-equipped Python 3.12+ interpreter.
Set `DRIFT_RUNTIME_TOKEN` in the launch environment for authenticated monitoring
without changing browser access. Alternatively, `DRIFT_API_TOKEN` protects every
API and takes precedence for monitoring too. Never put tokens in argv. Keep
provider credentials in the existing environment, not these flags.

```bash
'C:/Users/pc/AppData/Local/Programs/Python/Python312/python.exe' -m drift.local_runtime \
  --projects-root C:/Users/pc/Documents/projects \
  --box C:/Users/pc/Documents/projects/Drift/local_box \
  --state-dir C:/Users/pc/AppData/Local/hermes/profiles/chimera/drift-runtime \
  --base-url http://127.0.0.1:47113/v1 --model command-a-03-2025 \
  --daily-calls 12 --weekly-calls 60 --model-timeout 30 --attempts 1 \
  --max-output 1800 --pace 5 --port 47116 --startup-timeout 180 \
  --max-restarts 5 --backoff 2 --max-backoff 60 --poll 5 \
  --log-bytes 2000000 --log-backups 3
```

This is the launch contract, not an instruction to overlap the existing pilot.
Stop/hand off the existing Drift runner before launching. The supervisor refuses
an occupied HTTP port, another supervisor for this box, or a surviving worker.

Optional gateway recovery (append both flags to the command above):

```bash
--gateway-cwd C:/Users/pc/Documents/projects/DMR-X \
--gateway-health-url http://127.0.0.1:47113/healthz \
--gateway-command '["C:/Users/pc/.bun/bin/bun.exe","--env-file=C:/Users/pc/Documents/projects/DMR-X/.env","run","start"]'
```

The command is a JSON argv array, executed without a shell. Spawned children get
`DMRX_HOST=127.0.0.1`, `DMRX_FREE_TIER_STRATEGY=free_only`; gateway `PORT` comes
from `--base-url` (47113 above). The command must remain foreground, not daemonize.
An existing reachable HTTP listener is reused, including transient HTTP 503 during
warmup. An owned gateway that remains running is never killed for slow readiness;
only process exit/offline permits a bounded replacement. No companion services are
started. No gateway command means externally managed inference, with no recovery.

Required flags: projects-root (existing directory), box, state-dir (outside box),
base-url (loopback only), model, daily-calls and weekly-calls (nonnegative integers).
Shell, embeddings, remote decisions and model scoring are disabled; free-only is
forced. Attempt count is 1 or 2; output cap 1..4000; model timeout is <=60 seconds.
All timing values must be finite and positive. Defaults not shown above: pace=45,
model-timeout=30, attempts=1, max-output=1000. The explicit launch above overrides them.
No budget files are reset; blocked work is not approved automatically.

`GET /api/runtime` uses the existing same-origin guard and always requires the
configured API or runtime bearer token. Without either token it refuses to expose
status. A dedicated runtime token does not disable or bypass a configured API
token. It returns HTTP 200 only
when every configured brain task is alive and shutdown has not begun; otherwise
503. Per-brain states are starting/running/failed/stopped/cancelled. Errors retain
exception class and timestamp only, never message, traceback, prompts or paths.
Completed task handles/errors remain observable until the next application startup;
sanitized task failure types are also emitted to rotating process logs.

The supervisor checks process exit and authenticated HTTP/brain liveness. After
startup grace, three failed probes cause stop/wait/restart. Inference availability
and budget admission are not restart triggers. Worker and gateway each have at most
`max-restarts + 1` lifetime starts, with capped exponential backoff; allowances do
not reset on recovery. Exhaustion exits 1; graceful interrupt exits 0.

Console/error logs rotate outside the box. Hidden OS lock files remain inside the
box and are ignored by the existing file scanner; OS locks release on process exit.
Ctrl+C/SIGTERM (Windows CTRL_BREAK) requests graceful shutdown, then owned children
are forcibly stopped after bounded waits. Windows headless launches without a console
may require terminate fallback. Preexisting shared gateway processes are never owned
or stopped. This is local process supervision, not a sandbox or a 24-hour soak.
