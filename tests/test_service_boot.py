"""A read-only Drift service must not depend on creating a shell venv."""
import asyncio
from drift.brain import Brain
from drift.config import config


def test_readonly_boot_skips_shell_environment(tmp_path, monkeypatch):
    import drift.brain as module
    monkeypatch.setitem(config, 'shell_enabled', False)
    monkeypatch.setitem(config, 'thinking_pace_seconds', 0)
    monkeypatch.setattr(module, 'ensure_venv', lambda *a: (_ for _ in ()).throw(RuntimeError('venv not needed')))
    b = Brain({'name': 'bootstrap', 'animal': 'crab'}, str(tmp_path))
    async def stop_cycle():
        b.running = False
    b._think_once = stop_cycle
    b._idle_wander = stop_cycle
    asyncio.run(b.run())
    assert b.tasks is not None and b.stream is not None


def test_failed_cycle_does_not_kill_service(tmp_path, monkeypatch):
    monkeypatch.setitem(config, 'shell_enabled', False)
    monkeypatch.setitem(config, 'thinking_pace_seconds', 0)
    b = Brain({'name': 'survival', 'animal': 'crab'}, str(tmp_path))
    async def fail():
        raise RuntimeError('cycle fixture failed')
    async def stop():
        b.running = False
    b._think_once = fail
    b._idle_wander = stop
    asyncio.run(b.run())
    assert b.state == 'idle'
