# Keep a local Drift worker running

The optional supervisor watches the HTTP service and its background worker. It can restart a worker that exits or stops responding. It does not fix a provider outage or approve blocked work for you.

Use a source checkout with its dependencies installed and a built frontend. Stop any existing Drift runner before starting another. The supervisor refuses an occupied port, another supervisor for the box or a surviving worker.

## Start it

Set `DRIFT_RUNTIME_TOKEN` in the launch environment for monitoring. Alternatively, set `DRIFT_API_TOKEN` to protect every API; it takes precedence. Keep tokens out of command-line arguments and committed files.

From the checkout, using Python 3.12 or 3.13:

```bash
python -m drift.local_runtime \
  --projects-root .. --box ./local_box --state-dir ../drift-runtime \
  --base-url http://127.0.0.1:47113/v1 --model auto-free \
  --daily-calls 12 --weekly-calls 60 \
  --model-timeout 30 --attempts 1 --max-output 1800 \
  --pace 5 --port 47116 --startup-timeout 180 \
  --max-restarts 5 --backoff 2 --max-backoff 60 --poll 5 \
  --log-bytes 2000000 --log-backups 3
```

These are example limits, not a replacement for an existing launcher's settings. Use the same box when restarting. The projects root must exist; state and logs must sit outside the box. The gateway URL must be local. Choose a model that your gateway actually offers.

The supervisor forces free-only mode and disables shell execution, embeddings, model scoring and remote decisions. It does not reset call accounting or approve blocked tasks. One request can make one or two provider attempts, output is capped at 4,000 tokens and the model timeout cannot exceed 60 seconds.

## What counts as healthy

`GET /api/runtime` needs the configured bearer token and the usual origin checks. It returns HTTP 200 only while every configured worker task is alive and shutdown has not begun; otherwise it returns 503. Failures expose the exception class and time, not private messages or tracebacks.

After the startup grace period, three failed liveness probes cause a worker restart. Inference availability and exhausted budgets do not trigger restarts. With `--max-restarts 5`, a worker or owned gateway has at most six starts during that supervisor run. Exhaustion exits with status 1.

Console and error logs rotate outside the box. Ctrl+C requests shutdown. On a headless Windows launch, console signals may be unavailable, so a bounded terminate fallback may be needed.

## Optional gateway recovery

Without `--gateway-command`, you manage the gateway yourself. To let Drift start it after an outage, supply both `--gateway-cwd` and `--gateway-command`. The latter is a JSON array of executable and arguments, not a shell command. Keep that process in the foreground and use the actual command for your gateway installation.

Spawned gateways receive loopback/free-only settings and the port from `--base-url`. The supervisor reuses an existing listener, tolerates HTTP 503 during warmup and does not kill a running gateway just because readiness is slow. It stops only gateway processes it started itself.

This is process supervision, not a sandbox or proof of weeks of unattended operation. Keep backups and check health, approvals and disk space.
