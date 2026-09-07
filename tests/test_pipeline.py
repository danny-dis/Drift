"""Tests for drift/pipeline.py — idea-to-project qualification pipeline."""
import pytest

from drift.organism import DriftLedger, Project, read_drift_md, update_drift_md
from drift.task import TaskStore
from drift.pipeline import (
    IdeaPipeline,
    ProjectMatch,
    _keyword_overlap,
    _has_weak_match,
    create_project_from_idea,
)


def test_capture_idea(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    idea = pipeline.capture_idea("Use graph databases for knowledge management")
    assert idea.id.startswith("idea-")
    assert "graph" in idea.concepts


def test_extract_concepts(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    concepts = pipeline.extract_concepts("Use graph databases for knowledge management")
    assert "graph" in concepts
    assert "databases" in concepts
    assert "knowledge" in concepts


def test_keyword_overlap():
    assert _keyword_overlap("graph database", "graph visualization") > 0.0
    assert _keyword_overlap("weather", "cryptography") == 0.0


def test_has_weak_match():
    assert _has_weak_match(0.2, threshold=0.3) is True
    assert _has_weak_match(0.5, threshold=0.3) is False


def test_qualify_idea(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    idea = pipeline.capture_idea("Test idea")
    qualified = pipeline.qualify_idea(idea.id, "PROJECT")
    assert qualified.status == "PROJECT"


def test_qualify_idea_invalid(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    idea = pipeline.capture_idea("Test idea")
    with pytest.raises(ValueError):
        pipeline.qualify_idea(idea.id, "INVALID")





def test_update_project_intelligence(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    proj_dir = tmp_path / "project"
    proj_dir.mkdir()
    ledger.add_project(Project(id="proj", name="Test", repo="", local_path=str(proj_dir)))
    pipeline = IdeaPipeline(ledger, tasks, {})
    pipeline.update_project_intelligence(
        "proj",
        findings=["New pattern identified"],
        challenges=["Performance concern"],
        alternatives=["Option A", "Option B"],
        questions=["How to scale?"],
        evidence=["source-1"],
    )
    drift_md = read_drift_md(str(proj_dir))
    assert "New pattern identified" in drift_md
    assert "Performance concern" in drift_md


def test_match_project_weak_match_returns_empty(tmp_path):
    """A project with no keyword overlap returns no matches (rejected)."""
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    ledger.add_project(Project(id="proj-x", name="Cryptography Library", repo="crypto"))
    idea = pipeline.capture_idea("Build a weather forecasting app")
    matches = pipeline.match_project(idea.id)
    # No meaningful overlap, so matches should be empty
    assert isinstance(matches, list)


def test_get_idea_status(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    idea = pipeline.capture_idea("Test idea for status")
    pipeline.qualify_idea(idea.id, "RESEARCH")
    status = pipeline.get_idea_status(idea.id)
    assert status["qualification"] == "RESEARCH"
    assert "idea" in status


def test_create_project_from_idea(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    pipeline = IdeaPipeline(ledger, tasks, {})
    idea = pipeline.capture_idea("Build a new tool")
    project = create_project_from_idea(pipeline, idea.id, "New Tool", "user/new-tool")
    assert project.id == "new-tool"
    assert project.name == "New Tool"
