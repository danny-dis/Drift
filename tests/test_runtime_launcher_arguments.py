"""Offline regression for the exact callable-main launcher path."""
import sys
import pytest


def test_explicit_launcher_arguments_reach_real_worker_command(tmp_path, monkeypatch):
    from drift import local_runtime as runtime
    monkeypatch.setenv('DRIFT_RUNTIME_TOKEN', 'synthetic-monitor-token')
    monkeypatch.delenv('DRIFT_API_TOKEN', raising=False)
    argv = ['--projects-root', str(tmp_path), '--box', str(tmp_path / 'box'),
            '--state-dir', str(tmp_path / 'logs'), '--model', 'offline-fixture',
            '--base-url', 'http://127.0.0.1:1/v1', '--daily-calls', '0',
            '--weekly-calls', '0', '--port', '65534']
    monkeypatch.setattr(sys, 'argv', ['unrelated-bootstrap.py'])
    args = runtime.parse_args(argv)
    monkeypatch.setattr(runtime, 'listening', lambda _: False)

    class CommandObserved(Exception):
        pass

    def spawn(command, *unused, **kwargs):
        assert command == [sys.executable, '-m', 'drift.local_runtime', *argv, '--worker']
        raise CommandObserved()

    monkeypatch.setattr(runtime, 'spawn', spawn)
    with pytest.raises(CommandObserved):
        runtime.supervise(args)
