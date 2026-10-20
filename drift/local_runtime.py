"""Bounded local process supervision; run with python -m drift.local_runtime."""
import argparse
from contextlib import contextmanager
import http.client
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('projects-root', 'box', 'state-dir', 'model', 'base-url'):
        parser.add_argument('--' + name, required=True)
    for name in ('daily-calls', 'weekly-calls'):
        parser.add_argument('--' + name, required=True, type=int)
    for name, default in (('port', 47116), ('attempts', 1), ('max-output', 1000),
                          ('max-restarts', 5), ('log-bytes', 2_000_000), ('log-backups', 3)):
        parser.add_argument('--' + name, type=int, default=default)
    for name, default in (('pace', 45), ('model-timeout', 30), ('poll', 5),
                          ('startup-timeout', 180), ('backoff', 2), ('max-backoff', 60)):
        parser.add_argument('--' + name, type=float, default=default)
    parser.add_argument('--gateway-command', type=json.loads, help='JSON argv array; never a shell string')
    parser.add_argument('--gateway-cwd', type=Path)
    parser.add_argument('--gateway-health-url')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.worker_argv = list(sys.argv[1:] if argv is None else argv)
    for name in ('projects_root', 'box', 'state_dir'):
        setattr(args, name, Path(getattr(args, name)).resolve())
    if not args.projects_root.is_dir() or args.state_dir.is_relative_to(args.box):
        raise ValueError('Projects root must exist; logs/state must be outside the watched box')
    if not (os.environ.get('DRIFT_API_TOKEN') or os.environ.get('DRIFT_RUNTIME_TOKEN', '')).strip():
        raise ValueError('DRIFT_API_TOKEN or DRIFT_RUNTIME_TOKEN is required in the environment')
    if args.daily_calls < 0 or args.weekly_calls < 0 or not 1 <= args.port <= 65535:
        raise ValueError('Invalid call limits or port')
    if not 0 <= args.max_restarts <= 100 or args.log_bytes < 1 or args.log_backups < 1:
        raise ValueError('Invalid restart or log limits')
    if args.attempts not in (1, 2) or not 1 <= args.max_output <= 4000 or not args.model.strip():
        raise ValueError('Invalid model settings')
    for name in ('pace', 'model_timeout', 'poll', 'startup_timeout', 'backoff', 'max_backoff'):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Timing settings must be finite and positive')
    if args.model_timeout > 60 or args.max_backoff < args.backoff:
        raise ValueError('Model timeout is capped at 60; max backoff must cover initial backoff')
    base = urlsplit(args.base_url)
    args.gateway_health_url = args.gateway_health_url or f'{base.scheme}://{base.netloc}/healthz'
    for url in (args.base_url, args.gateway_health_url):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Gateway URLs must be local and contain no credentials/query/fragment')
    if args.gateway_command is not None and (not isinstance(args.gateway_command, list) or not args.gateway_command or not all(isinstance(x, str) and x for x in args.gateway_command)):
        raise ValueError('Gateway command must be a nonempty JSON argv array')
    return args


@contextmanager
def instance_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if not stream.tell():
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('This box is already running') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def check_projects(projects, root):
    for project in projects:
        value = project.get('local_path')
        if isinstance(value, str):
            value = value.strip()
        if value and (not isinstance(value, str) or not Path(value).resolve().is_relative_to(root)):
            raise ValueError('Project path is outside the allowed projects root')


def install_project_guard(app, root):
    from starlette.responses import JSONResponse

    @app.middleware('http')
    async def project_scope(request, call_next):
        if request.method == 'POST' and request.url.path.rstrip('/') in ('/api/ui/projects', '/api/organism/projects'):
            try:
                body = await request.json()
                if not isinstance(body, dict):
                    raise TypeError()
                check_projects([body], root)
            except ValueError:
                return JSONResponse({'detail': 'Project path outside allowed root or invalid JSON'}, status_code=403)
            except (TypeError, OSError):
                return JSONResponse({'detail': 'Invalid project registration'}, status_code=400)
        return await call_next(request)


def application(args):
    from drift.config import config
    config.update(provider='custom', base_url=args.base_url, model=args.model,
                  environment_path=str(args.box), shell_enabled=False, free_only=True,
                  cost_filter='free', free_tier_strategy='free_only',
                  daily_max_model_calls=args.daily_calls, weekly_max_model_calls=args.weekly_calls,
                  thinking_pace_seconds=args.pace, model_timeout_seconds=args.model_timeout,
                  max_provider_attempts=args.attempts, max_output_tokens=args.max_output,
                  embeddings_enabled=False, llm_scoring_enabled=False,
                  decision_models_enabled=False, decision_remote_opt_in=False)
    from drift.brain import Brain
    from drift.identity import load_identity_from
    from drift.organism import DriftLedger
    from drift.server import create_app
    args.box.mkdir(parents=True, exist_ok=True)
    check_projects(DriftLedger(str(args.box)).data['projects'], args.projects_root)
    identity = load_identity_from(str(args.box)) or {'name': 'Drift', 'animal': 'crab'}
    brain = Brain(identity, str(args.box))
    app = create_app({'local': brain})
    install_project_guard(app, args.projects_root)
    return app


def log_handler(root, name, size, backups):
    Path(root).mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(Path(root) / f'{name}.log', maxBytes=size,
                                  backupCount=backups, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    return handler


def probe(url, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    parsed = urlsplit(url)
    connection = (http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection)(parsed.hostname, parsed.port, timeout=2)
    try:
        connection.request('GET', parsed.path or '/', headers=headers)
        response = connection.getresponse()
        if token and response.status in (200, 503):
            return json.loads(response.read(65536))
        if not token and 200 <= response.status < 300:
            return True
    except (http.client.HTTPException, OSError, ValueError):
        pass
    finally:
        connection.close()
    return None


def spawn(command, handlers, cwd=None, gateway_port=None):
    env = dict(os.environ, DMRX_HOST='127.0.0.1', DMRX_FREE_TIER_STRATEGY='free_only', PYTHONUNBUFFERED='1')
    if gateway_port is not None:
        env['PORT'] = str(gateway_port)
    child = subprocess.Popen(command, cwd=cwd, env=env, shell=False,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
    threads = []
    for stream, handler in zip((child.stdout, child.stderr), handlers):
        def drain(source=stream, target=handler):
            with source:
                while chunk := source.readline(4096):
                    target.handle(logging.makeLogRecord({'msg': chunk.decode('utf-8', errors='replace').rstrip(), 'levelno': logging.INFO}))
        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        threads.append(thread)
    return child, threads


def stop(child):
    if child is not None and child.poll() is None:
        try:
            child.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
        except OSError:
            child.terminate()  # Windows headless launches may have no console for CTRL_BREAK.
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def listening(url):
    parsed = urlsplit(url)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=1):
            return True
    except OSError:
        return False


def supervise(args, command=None):
    handlers = [log_handler(args.state_dir, name, args.log_bytes, args.log_backups)
                for name in ('console', 'error')]
    worker = gateway = None
    threads = []
    try:
        with instance_lock(args.box / '.drift-runtime.lock'):
            # The worker's second lock also fences orphans after a supervisor crash.
            with instance_lock(args.box / '.drift-worker.lock'):
                pass
            if command is None and listening(f'http://127.0.0.1:{args.port}'):
                raise RuntimeError('Local port already in use; refusing to overlap an existing service')
            command = command or [sys.executable, '-m', 'drift.local_runtime', *args.worker_argv, '--worker']
            gateway_attempts = 0
            gateway_retry = 0
            for attempt in range(args.max_restarts + 1):
                worker, worker_readers = spawn(command, handlers)
                threads.extend(worker_readers)
                started = time.monotonic()
                failures = 0
                while worker.poll() is None:
                    now = time.monotonic()
                    if args.gateway_command and now >= gateway_retry and (gateway is None or gateway.poll() is not None) and gateway_attempts <= args.max_restarts:
                        if not probe(args.gateway_health_url) and not listening(args.gateway_health_url):
                            gateway, readers = spawn(args.gateway_command, handlers, args.gateway_cwd, urlsplit(args.base_url).port or 80)
                            threads.extend(readers)
                            gateway_attempts += 1
                            gateway_retry = now + min(args.max_backoff, args.backoff * 2 ** (gateway_attempts - 1))
                    token = os.environ.get('DRIFT_API_TOKEN') or os.environ['DRIFT_RUNTIME_TOKEN']
                    health = probe(f'http://127.0.0.1:{args.port}/api/runtime', token)
                    alive = isinstance(health, dict) and health.get('healthy') is True
                    failures = 0 if alive else failures + 1
                    if not alive and now - started >= args.startup_timeout and failures >= 3:
                        handlers[1].handle(logging.makeLogRecord({'msg': 'HTTP/brain liveness failed; restarting owned worker', 'levelno': logging.ERROR}))
                        break
                    time.sleep(args.poll)
                stop(worker)
                for reader in worker_readers:
                    reader.join(timeout=2)
                if attempt < args.max_restarts:
                    time.sleep(min(args.max_backoff, args.backoff * 2 ** attempt))
            return 1  # Lifetime restart allowance exhausted; never reset budgets or allowance.
    except KeyboardInterrupt:
        return 0
    finally:
        stop(worker)
        stop(gateway)  # Only handles created here, never a preexisting shared gateway.
        for thread in threads:
            thread.join(timeout=2)
        for handler in handlers:
            handler.close()


def main(argv=None):
    args = parse_args(argv)
    if args.worker:
        import uvicorn
        with instance_lock(args.box / '.drift-worker.lock'):
            uvicorn.run(application(args), host='127.0.0.1', port=args.port, log_level='info', timeout_graceful_shutdown=10)
        return 0

    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    if os.name == 'nt':
        signal.signal(signal.SIGBREAK, interrupted)
    return supervise(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print(f'Local runtime refused ({type(error).__name__}); check settings, locks, paths and ports', file=sys.stderr)
        sys.exit(1)
