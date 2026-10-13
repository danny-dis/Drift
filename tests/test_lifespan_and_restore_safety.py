"""Regression coverage for service-owned tasks and safe backup extraction."""

import asyncio
import io
import tarfile

import httpx
import pytest

from drift import server
from drift.security import create_backup, restore_backup


class FakeBrain:
    def __init__(self, name):
        self.identity = {"name": name}
        self.ledger = object()
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.task = None

    async def run(self):
        self.task = asyncio.current_task()
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


@pytest.mark.parametrize("release_delay", [False, True])
def test_lifespan_tracks_and_cancels_delayed_startup(monkeypatch, release_delay):
    async def scenario():
        original_sleep = asyncio.sleep
        gate = asyncio.Event()
        delay_entered = asyncio.Event()
        delay_cancelled = asyncio.Event()
        delays = []

        async def controlled_sleep(seconds):
            delays.append(seconds)
            delay_entered.set()
            try:
                await gate.wait()
            except asyncio.CancelledError:
                delay_cancelled.set()
                raise

        monkeypatch.setattr(server.asyncio, "sleep", controlled_sleep)
        initial = {FakeBrain("one"), FakeBrain("two")}
        monkeypatch.setattr(server, "brains", {b.identity["name"]: b for b in initial})
        monkeypatch.setattr(server, "_tasks", set())
        before = asyncio.all_tasks()
        owned = set()
        try:
            async with server.app.router.lifespan_context(server.app):
                await asyncio.wait_for(delay_entered.wait(), 1)
                assert delays == [0.5]
                assert not any(b.started.is_set() for b in initial)
                assert len(server._tasks) == 1
                owned.update(server._tasks)
                if release_delay:
                    gate.set()
                    await asyncio.wait_for(
                        asyncio.gather(*(b.started.wait() for b in initial)), 1
                    )
                    await original_sleep(0)
                    assert {b.task for b in initial} == server._tasks
                    owned.update(server._tasks)
            assert not server._tasks
            assert all(t.done() for t in owned)
            if release_delay:
                assert all(b.cancelled.is_set() for b in initial)
            else:
                assert delay_cancelled.is_set()
                assert not any(b.started.is_set() for b in initial)
        finally:
            leaked = asyncio.all_tasks() - before
            for task in leaked:
                task.cancel()
            await asyncio.gather(*leaked, return_exceptions=True)

    asyncio.run(scenario())


def test_lifespan_cancels_api_created_brain(monkeypatch, tmp_path):
    async def scenario():
        brain = FakeBrain("created")
        delay_entered = asyncio.Event()
        delay_cancelled = asyncio.Event()

        async def controlled_sleep(seconds):
            delay_entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                delay_cancelled.set()

        monkeypatch.setattr(server.asyncio, "sleep", controlled_sleep)
        monkeypatch.setattr(server, "brains", {})
        monkeypatch.setattr(server, "_tasks", set())
        monkeypatch.setattr(server, "Brain", lambda identity, box: brain)
        monkeypatch.setattr(server.app.state, "drift_brains", {}, raising=False)
        monkeypatch.delenv("DRIFT_API_TOKEN", raising=False)
        monkeypatch.setattr("drift.runtime_resources.workspace_root", lambda: tmp_path)
        async with server.app.router.lifespan_context(server.app):
            await asyncio.wait_for(delay_entered.wait(), 1)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=server.app),
                base_url="http://127.0.0.1",
            ) as client:
                response = await client.post("/api/crabs", json={"name": "created"})
            assert response.status_code == 200
            assert response.json()["ok"] is True
            await asyncio.wait_for(brain.started.wait(), 1)
            owned = set(server._tasks)
            assert len(owned) == 2
            assert brain.task in owned
        assert delay_cancelled.is_set()
        assert brain.cancelled.is_set()
        assert all(task.done() for task in owned)
        assert not server._tasks

    asyncio.run(scenario())


def test_create_app_remains_singleton_without_duplicate_routes(monkeypatch):
    monkeypatch.setattr(server, "brains", {})
    monkeypatch.setattr(server.app.state, "drift_brains", {}, raising=False)
    first = {"first": FakeBrain("first")}
    second = {"second": FakeBrain("second")}
    application = server.create_app(first)
    route_count = len(application.routes)
    assert server.create_app(second) is application is server.app
    assert len(application.routes) == route_count
    assert application.state.drift_brains is second
    assert application.router.on_startup == []
    assert application.router.on_shutdown == []


def test_backup_rejects_parent_traversal(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("../escaped.txt")
        member.size = 6
        tar.addfile(member, io.BytesIO(b"unsafe"))
    with pytest.raises(tarfile.FilterError):
        restore_backup(str(archive), str(tmp_path / "restore"))
    assert not (tmp_path / "escaped.txt").exists()


def test_backup_rejects_escaping_symlink(tmp_path):
    archive = tmp_path / "unsafe-link.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("escape")
        member.type = tarfile.SYMTYPE
        member.linkname = "../outside"
        tar.addfile(member)
    with pytest.raises(tarfile.FilterError):
        restore_backup(str(archive), str(tmp_path / "restore"))
    assert not (tmp_path / "restore" / "escape").is_symlink()


def test_backup_roundtrip_preserves_nested_data(tmp_path):
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "state.json").write_bytes(b'{"ok": true}\n')
    (source / ".credentials.json").write_text("excluded", encoding="utf-8")
    archive = create_backup(str(source), str(tmp_path / "backup.tar.gz"))
    destination = tmp_path / "restore"
    restore_backup(archive, str(destination))
    assert (destination / "nested" / "state.json").read_bytes() == b'{"ok": true}\n'
    assert not (destination / ".credentials.json").exists()
