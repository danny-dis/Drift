"""Tests for drift/ui_api.py — production UI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from drift.server import create_app
from drift.brain import Brain
from drift.organism import DriftLedger, Project
from drift.task import TaskStore
from drift.memory import MemoryStream
from drift.receipt import ReceiptStore


@pytest.fixture
def client(tmp_path):
    """Create a test client with a mock brain."""
    env_path = str(tmp_path / "env")
    import os
    os.makedirs(env_path, exist_ok=True)

    brain = MagicMock(spec=Brain)
    brain.env_path = env_path
    brain.ledger = DriftLedger(env_path)
    brain.tasks = TaskStore(env_path)
    brain.receipts = ReceiptStore(env_path)
    brain.stream = MemoryStream(env_path)
    brain.attention = None

    # Add some test data
    brain.ledger.add_project(Project(id="p1", name="Test Project", repo="test/repo"))
    brain.ledger.add_idea("Build a graph database", ["graph", "database"])

    # Mock attention methods to avoid real AttentionEconomy
    brain.attention = MagicMock()
    brain.attention.get_status.return_value = {
        "daily_budget": 1.0,
        "daily_remaining": 1.0,
        "weekly_budget": 5.0,
        "weekly_remaining": 5.0,
        "total_spend": 0.0,
    }
    brain.attention.generate_candidates.return_value = []

    app = create_app({"test": brain})
    return TestClient(app)


class TestProjectEndpoints:
    def test_list_projects(self, client):
        response = client.get("/api/ui/projects")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) >= 1

    def test_get_project(self, client):
        response = client.get("/api/ui/projects/p1")
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["id"] == "p1"
        assert "events" in data
        assert "ideas" in data

    def test_get_project_not_found(self, client):
        response = client.get("/api/ui/projects/nonexistent")
        assert response.status_code == 404


class TestIdeaEndpoints:
    def test_list_ideas(self, client):
        response = client.get("/api/ui/ideas")
        assert response.status_code == 200
        data = response.json()
        assert "ideas" in data

    def test_create_idea(self, client):
        response = client.post("/api/ui/ideas", json={"text": "New idea for testing"})
        assert response.status_code == 200
        data = response.json()
        assert data["idea"]["text"] == "New idea for testing"

    def test_create_idea_empty(self, client):
        response = client.post("/api/ui/ideas", json={"text": ""})
        assert response.status_code == 400

    def test_qualify_idea(self, client):
        # First create an idea
        response = client.post("/api/ui/ideas", json={"text": "Test idea"})
        idea_id = response.json()["idea"]["id"]

        response = client.post(f"/api/ui/ideas/{idea_id}/qualify", json={"qualification": "PROJECT"})
        assert response.status_code == 200
        assert response.json()["idea"]["status"] == "PROJECT"


class TestResearchEndpoints:
    def test_list_research(self, client):
        response = client.get("/api/ui/research")
        assert response.status_code == 200
        data = response.json()
        assert "findings" in data

    def test_list_evidence(self, client):
        response = client.get("/api/ui/research/evidence")
        assert response.status_code == 200
        data = response.json()
        assert "evidence" in data


class TestBudgetEndpoints:
    def test_get_budget(self, client):
        response = client.get("/api/ui/budget")
        assert response.status_code == 200

    def test_get_candidates(self, client):
        response = client.get("/api/ui/attention/candidates")
        assert response.status_code == 200
        data = response.json()
        assert "candidates" in data


class TestReceiptEndpoints:
    def test_list_receipts(self, client):
        response = client.get("/api/ui/receipts")
        assert response.status_code == 200
        data = response.json()
        assert "receipts" in data
        assert "total_estimated_cost" in data

    def test_get_task_receipts(self, client):
        response = client.get("/api/ui/receipts/task-000001")
        assert response.status_code == 200
        data = response.json()
        assert "receipts" in data


class TestApprovalEndpoints:
    def test_list_approvals(self, client):
        response = client.get("/api/ui/approvals")
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data


class TestNotificationEndpoints:
    def test_list_notifications(self, client):
        response = client.get("/api/ui/notifications")
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data


class TestCapabilityEndpoints:
    def test_list_capabilities(self, client):
        response = client.get("/api/ui/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert "capabilities" in data
        assert "classify_idea" in data["capabilities"]


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/api/ui/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data


class TestUsageEndpoint:
    def test_get_usage(self, client):
        response = client.get("/api/ui/usage")
        assert response.status_code == 200
        data = response.json()
        assert "total_calls" in data
        assert "total_cost" in data
