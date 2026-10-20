"""Disposable-only runtime regressions; no provider requests or owner boxes."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


def test_dead_brain_is_unhealthy_while_http_remains_up(monkeypatch):
    from drift import server
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    brain = SimpleNamespace(identity={'name': 'test'}, state='idle', thought_count=0,
                            stop=lambda: None)
    monkeypatch.setattr(server, 'brains', {'local': brain})
    monkeypatch.setattr(server, '_tasks', set())
    monkeypatch.setattr(server, '_brain_tasks', {}, raising=False)
    monkeypatch.setattr(server, '_task_failures', {}, raising=False)
    monkeypatch.setattr(server, '_shutting_down', False, raising=False)

    async def scenario():
        gate = asyncio.Event()

        async def worker():
            await gate.wait()
            raise RuntimeError('PRIVATE IDEA AND TOKEN')

        server._track_task(worker(), 'local')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),
                                    base_url='http://testserver') as client:
            assert (await client.get('/api/runtime')).status_code == 401
            headers = {'Authorization': 'Bearer test-token'}
            assert (await client.get('/api/runtime', headers={**headers, 'Origin': 'http://evil'})).status_code == 403
            assert (await client.get('/api/runtime', headers=headers)).json()['healthy']
            gate.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert (await client.get('/api/crabs', headers=headers)).status_code == 200
            result = await client.get('/api/runtime', headers=headers)
            assert result.status_code == 503
            data = result.json()
            assert data['brains']['local']['state'] == 'failed'
            assert data['brains']['local']['error']['type'] == 'RuntimeError'
            assert 'PRIVATE' not in result.text
            assert (await client.get('/api/runtime', headers=headers)).json() == data
            await server._shutdown()
            stopped = (await client.get('/api/runtime', headers=headers)).json()
            assert stopped['shutting_down'] and not stopped['healthy']
            assert stopped['brains']['local']['error']['type'] == 'RuntimeError'
    asyncio.run(scenario())


def test_shutdown_cancels_brain_and_retains_cancelled_liveness(monkeypatch):
    from drift import server
    monkeypatch.setattr(server, 'brains', {})
    monkeypatch.setattr(server, '_tasks', set())
    monkeypatch.setattr(server, '_brain_tasks', {}, raising=False)
    monkeypatch.setattr(server, '_task_failures', {}, raising=False)
    monkeypatch.setattr(server, '_shutting_down', False, raising=False)

    async def scenario():
        task = server._track_task(asyncio.sleep(100), 'local')
        await server._shutdown()
        assert task.cancelled()
        assert server._brain_tasks['local'] is task
    asyncio.run(scenario())


def settings(tmp_path, *extra):
    from drift.local_runtime import parse_args
    root = tmp_path / 'projects'
    root.mkdir(exist_ok=True)
    return parse_args(['--projects-root', str(root), '--box', str(tmp_path / 'box'),
                       '--state-dir', str(tmp_path / 'state'), '--model', 'explicit-model',
                       '--daily-calls', '12', '--weekly-calls', '60',
                       '--base-url', 'http://127.0.0.1:1/v1', *extra])


def test_duplicate_start_refused_across_processes_and_lock_released(tmp_path):
    import subprocess
    from drift.local_runtime import instance_lock
    path = tmp_path / '.runtime.lock'
    script = ('from drift.local_runtime import instance_lock; import sys; '
              'lock=instance_lock(sys.argv[1]); lock.__enter__()')
    with instance_lock(path):
        result = subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True)
        assert result.returncode != 0 and b'already running' in result.stderr
    with instance_lock(path):
        pass


def test_console_and_error_logs_roll_over(tmp_path):
    from drift.local_runtime import log_handler
    import logging
    for name in ('console', 'error'):
        handler = log_handler(tmp_path, name, 100, 2)
        try:
            for _ in range(30):
                handler.handle(logging.makeLogRecord({'msg': 'x' * 40, 'levelno': 20}))
            assert (tmp_path / f'{name}.log.1').exists()
            assert len(list(tmp_path.glob(f'{name}.log*'))) == 3
        finally:
            handler.close()


def test_config_rejects_unsafe_paths_and_invalid_caps(tmp_path, monkeypatch):
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    args = settings(tmp_path)
    assert args.model == 'explicit-model' and args.daily_calls == 12
    with pytest.raises(ValueError, match='outside'):
        settings(tmp_path, '--state-dir', str(tmp_path / 'box' / 'logs'))
    with pytest.raises(ValueError):
        settings(tmp_path, '--daily-calls', '-1')
    with pytest.raises(ValueError):
        settings(tmp_path, '--base-url', 'https://remote.invalid/v1')


def test_both_folder_apis_and_startup_reject_outside_projects(tmp_path, monkeypatch):
    from drift.local_runtime import install_project_guard, check_projects
    from fastapi import FastAPI, Request
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    args = settings(tmp_path)
    outside = tmp_path / 'private'
    outside.mkdir()
    with pytest.raises(ValueError, match='outside'):
        check_projects([{'local_path': str(outside)}], args.projects_root)
    from drift.local_runtime import application
    from drift.config import config
    args.box.mkdir()
    ledger = args.box / 'drift_ledger.json'
    ledger.write_text(json.dumps({'schema': 2, 'ideas': [], 'events': [],
                                  'projects': [{'local_path': str(outside)}],
                                  'mind_map': {'nodes': [], 'edges': []}}))
    original = dict(config)
    try:
        with pytest.raises(ValueError, match='outside'):
            application(args)
        assert config['shell_enabled'] is False and config['free_only'] is True
        assert config['model'] == 'explicit-model'
        assert config['daily_max_model_calls'] == 12 and config['weekly_max_model_calls'] == 60
    finally:
        config.clear()
        config.update(original)
    application = FastAPI()

    @application.post('/api/ui/projects')
    @application.post('/api/organism/projects')
    async def registered(request: Request):
        return await request.json()

    install_project_guard(application, args.projects_root)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                    base_url='http://testserver') as client:
            for url in ('/api/ui/projects', '/api/organism/projects'):
                assert (await client.post(url, json={'local_path': str(outside)})).status_code == 403
                assert (await client.post(url + '/', json={'local_path': str(outside)})).status_code == 403
                assert (await client.post(url, json={'local_path': str(args.projects_root)})).status_code == 200
                assert (await client.post(url, json=[])).status_code == 400
    asyncio.run(scenario())


def test_child_crashes_restart_with_finite_backoff_and_logs(tmp_path, monkeypatch):
    from drift.local_runtime import supervise
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    args = settings(tmp_path, '--max-restarts', '2', '--backoff', '0.01',
                    '--max-backoff', '0.02', '--poll', '0.01')
    counter = tmp_path / 'starts.txt'
    script = ("from pathlib import Path; import sys; p=Path(sys.argv[1]); "
              "p.open('a').write('start\\n'); print('console'); "
              "print('error', file=sys.stderr); sys.exit(7)")
    assert supervise(args, [sys.executable, '-c', script, str(counter)]) == 1
    assert counter.read_text().splitlines() == ['start'] * 3
    assert 'console' in (args.state_dir / 'console.log').read_text()
    assert 'error' in (args.state_dir / 'error.log').read_text()


from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


@contextmanager
def local_http(payload, status=200):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            self.send_response(status)
            if status == 302:
                self.send_header('Location', '/redirected')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_supervisor_detects_dead_brain_despite_live_http(tmp_path, monkeypatch):
    from drift.local_runtime import supervise, probe
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    counter = tmp_path / 'starts'
    script = ("from pathlib import Path; import sys,time; "
              "Path(sys.argv[1]).open('a').write('start\\n'); time.sleep(100)")
    with local_http({'healthy': False, 'brains': {'local': {'alive': False}}}, 503) as (port, _):
        args = settings(tmp_path, '--port', str(port), '--startup-timeout', '15',
                        '--poll', '0.02', '--max-restarts', '1', '--backoff', '0.01')
        assert supervise(args, [sys.executable, '-c', script, str(counter)]) == 1
        assert counter.read_text().splitlines() == ['start', 'start']
        assert probe(f'http://127.0.0.1:{port}/api/runtime', 'test-token')['healthy'] is False
    assert 'liveness failed' in (args.state_dir / 'error.log').read_text()


def test_unavailable_inference_and_exhausted_budget_do_not_restart_live_worker(tmp_path, monkeypatch):
    from drift.local_runtime import supervise
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    completed = tmp_path / 'completed'
    script = "from pathlib import Path; import sys,time; time.sleep(.3); Path(sys.argv[1]).touch()"
    with local_http({'healthy': True, 'inference_available': False, 'remaining_calls': 0}) as (port, _):
        args = settings(tmp_path, '--port', str(port), '--startup-timeout', '0.01',
                        '--poll', '0.01', '--max-restarts', '0')
        assert supervise(args, [sys.executable, '-c', script, str(completed)]) == 1
    assert completed.exists()
    assert 'liveness failed' not in (args.state_dir / 'error.log').read_text()


@pytest.mark.parametrize('status', [200, 503])
def test_reuses_shared_gateway_without_starting_or_stopping_it(tmp_path, monkeypatch, status):
    from drift import local_runtime
    from drift.local_runtime import supervise, probe
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    marker = tmp_path / 'gateway-started'
    gateway = [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).touch()', str(marker)]
    calls, original_spawn = [], local_runtime.spawn
    def observed_spawn(command, *args, **kwargs):
        calls.append(command)
        return original_spawn(command, *args, **kwargs)
    monkeypatch.setattr(local_runtime, 'spawn', observed_spawn)
    with local_http({'status': 'ok'}, status) as (port, requests):
        args = settings(tmp_path, '--max-restarts', '0', '--poll', '0.01',
                        '--gateway-command', json.dumps(gateway),
                        '--gateway-health-url', f'http://127.0.0.1:{port}/health')
        assert supervise(args, [sys.executable, '-c', 'import time; time.sleep(.2)']) == 1
        assert not marker.exists()
        assert gateway not in calls
        assert probe(f'http://127.0.0.1:{port}/health') is (True if status == 200 else None)
        assert requests and all(auth is None for _, auth in requests)


def test_owned_gateway_crash_restarts_are_bounded(tmp_path, monkeypatch):
    from drift.local_runtime import supervise
    monkeypatch.setenv('DRIFT_API_TOKEN', 'test-token')
    marker = tmp_path / 'gateway-starts'
    script = ("from pathlib import Path; import os,sys; "
              "assert os.environ['DMRX_FREE_TIER_STRATEGY']=='free_only'; "
              "assert os.environ['DMRX_HOST']=='127.0.0.1' and os.environ['PORT']=='1'; "
              "Path(sys.argv[1]).open('a').write('start\\n'); sys.exit(7)")
    args = settings(tmp_path, '--max-restarts', '1', '--backoff', '0.01', '--poll', '0.01',
                    '--gateway-command', json.dumps([sys.executable, '-c', script, str(marker)]))
    worker = ("from pathlib import Path; import sys,time; p=Path(sys.argv[1]); end=time.monotonic()+8\n"
              "while time.monotonic()<end and (not p.exists() or len(p.read_text().splitlines())<2): time.sleep(.02)")
    assert supervise(args, [sys.executable, '-c', worker, str(marker)]) == 1
    assert marker.read_text().splitlines() == ['start', 'start']


def test_runtime_probe_does_not_forward_token_on_redirect():
    from drift.local_runtime import probe
    with local_http({}, 302) as (port, requests):
        assert probe(f'http://127.0.0.1:{port}/api/runtime', 'test-token') is None
        assert len(requests) == 1


def test_monitor_token_does_not_require_browser_login(tmp_path, monkeypatch):
    from drift import server
    monkeypatch.delenv('DRIFT_API_TOKEN', raising=False)
    monkeypatch.setenv('DRIFT_RUNTIME_TOKEN', 'test-monitor-token')
    settings(tmp_path)
    monkeypatch.setattr(server, 'brains', {'local': SimpleNamespace(
        identity={'name': 'test'}, state='idle', thought_count=0)})
    monkeypatch.setattr(server, '_brain_tasks', {})
    monkeypatch.setattr(server, '_task_failures', {})
    monkeypatch.setattr(server, '_shutting_down', False)

    async def scenario():
        task = asyncio.create_task(asyncio.sleep(60))
        server._brain_tasks['local'] = task
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),
                                        base_url='http://testserver') as client:
                assert (await client.get('/api/crabs')).status_code == 200
                assert (await client.get('/api/runtime')).status_code == 401
                result = await client.get('/api/runtime', headers={
                    'Authorization': 'Bearer test-monitor-token'})
                assert result.status_code == 200 and result.json()['healthy']
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
