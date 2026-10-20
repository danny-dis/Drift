"""Disposable real-persistence probes for registration normalization."""
import asyncio

import httpx
import pytest


@pytest.mark.parametrize('padding', [' ', '\t', '\n', '\u2003'])
@pytest.mark.parametrize('route', ['/api/ui/projects', '/api/organism/projects'])
def test_guard_checks_the_trimmed_path_that_registration_persists(tmp_path, monkeypatch, padding, route):
    from fastapi import FastAPI, Request
    from drift.local_runtime import install_project_guard
    from drift.organism import DriftLedger
    from drift.pipeline import register_project_record

    root, outside = tmp_path / 'projects', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    monkeypatch.chdir(root)
    ledger = DriftLedger(str(tmp_path / 'box'))
    app = FastAPI()

    @app.post('/api/ui/projects')
    @app.post('/api/organism/projects')
    async def register(request: Request):
        register_project_record(ledger, await request.json())
        return ledger.data['projects'][-1]

    install_project_guard(app, root)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url='http://testserver') as client:
            rejected = await client.post(route, json={
                'name': 'Rejected', 'local_path': padding + str(outside) + padding})
            assert rejected.status_code == 403
            assert ledger.data['projects'] == []
            assert DriftLedger(str(tmp_path / 'box')).data['projects'] == []
            accepted = await client.post(route, json={
                'name': 'Allowed', 'local_path': padding + str(root) + padding})
            assert accepted.status_code == 200
            assert accepted.json()['local_path'] == str(root)
    asyncio.run(scenario())


@pytest.mark.parametrize('padding', [' ', '\t', '\n', '\u2003'])
def test_startup_guard_rejects_padded_outside_paths(tmp_path, monkeypatch, padding):
    from drift.local_runtime import check_projects
    root = tmp_path / 'projects'
    root.mkdir()
    monkeypatch.chdir(root)
    with pytest.raises(ValueError, match='outside'):
        check_projects([{'local_path': padding + str(tmp_path / 'outside') + padding}], root)
