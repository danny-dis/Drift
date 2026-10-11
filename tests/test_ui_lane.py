"""Tests for the UI lane — input validation on drift/ui_api.py endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from drift.server import create_app
from drift.brain import Brain
from drift.organism import DriftLedger, Project
from drift.task import TaskStore
from drift.memory import MemoryStream
from drift.receipt import ReceiptStore


@pytest.fixture
def client(tmp_path):
    env_path = str(tmp_path / "env")
    import os
    os.makedirs(env_path, exist_ok=True)

    brain = MagicMock(spec=Brain)
    brain.env_path = env_path
    brain.ledger = DriftLedger(env_path)
    brain.tasks = TaskStore(env_path)
    brain.receipts = ReceiptStore(env_path)
    brain.stream = MemoryStream(env_path)
    brain.ledger.add_project(Project(id="p1", name="Test Project", repo="test/repo"))
    brain.ledger.add_idea("Build a graph database", ["graph", "database"])

    app = create_app({"test": brain})
    return TestClient(app)


class TestCreateIdeaValidation:
    def test_create_idea_non_string_text_returns_400(self, client):
        """Non-string text must be a 400, not a server crash."""
        response = client.post("/api/ui/ideas", json={"text": 123})
        assert response.status_code == 400
