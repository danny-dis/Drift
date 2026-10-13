from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from drift.attention import AttentionEconomy
from drift.organism import DriftLedger
from drift.receipt import ReceiptStore
from drift.task import TaskStore
from drift.ui_api import router


def test_attention_endpoint_uses_real_candidate_generator(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    ledger.add_idea("Build a local notebook for scattered thoughts", ["notebook"])
    brain = SimpleNamespace(
        ledger=ledger,
        tasks=TaskStore(str(tmp_path)),
        attention=AttentionEconomy(ReceiptStore(str(tmp_path))),
        watcher=None,
        stream=None,
        _inbox_pending=[],
    )
    app = FastAPI()
    app.state.drift_brains = {"qa": brain}
    app.include_router(router)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/ui/attention/candidates"
    )
    assert response.status_code == 200, response.text
    assert any(
        candidate["source"] == "unqualified_idea"
        and "local notebook" in candidate["description"]
        for candidate in response.json()["candidates"]
    )
    assert brain.tasks.list_tasks() == []
