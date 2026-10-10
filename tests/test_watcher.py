"""Tests for drift/watcher.py — continuous Git/project watcher."""
import os
import subprocess
from pathlib import Path

import pytest

from drift.organism import DriftLedger, Project
from drift.task import TaskStore
from drift.watcher import (
    GitChange,
    GitWatcher,
    _extract_components,
    _is_commit_significant,
    _run_git,
)
from drift.memory import MemoryStream


def test_run_git_in_non_repo(tmp_path):
    result = _run_git(str(tmp_path), "status")
    assert result == ""


def test_extract_components():
    files = ["src/main.py", "src/lib.py", "tests/test.py", "README.md"]
    components = _extract_components(files)
    assert "src" in components
    assert "tests" in components


def test_is_commit_significant():
    assert _is_commit_significant("fix: critical bug", [])
    assert _is_commit_significant("feat: new feature", [])
    assert not _is_commit_significant("update docs", [])


def test_git_watcher_register_project(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    watcher = GitWatcher(ledger, tasks, {})
    watcher.register_project("proj-1", str(tmp_path))
    assert "proj-1" in watcher.get_watched_projects()


def test_git_watcher_scan_unregistered_project(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    watcher = GitWatcher(ledger, tasks, {})
    changes = watcher.scan_project("nonexistent")
    assert changes == []


def test_git_watcher_scan_without_git_repo(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    ledger.add_project(Project(id="proj", name="test", repo="", local_path=str(tmp_path)))
    watcher = GitWatcher(ledger, tasks, {})
    watcher.register_project("proj", str(tmp_path))
    changes = watcher.scan_project("proj")
    assert changes == []


def test_git_watcher_scan_with_commits(tmp_path):
    """Test with a real git repo with commits."""
    # Initialize a git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: initial commit"], cwd=tmp_path, capture_output=True)

    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    proj_path = str(tmp_path / "project")
    Path(proj_path).mkdir()
    subprocess.run(["git", "init"], cwd=proj_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=proj_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=proj_path, capture_output=True)
    Path(proj_path, "file.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=proj_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: initial project commit"], cwd=proj_path, capture_output=True)

    ledger.add_project(Project(id="proj", name="test", repo="", local_path=proj_path))
    watcher = GitWatcher(ledger, tasks, {})
    watcher.register_project("proj", proj_path)
    changes = watcher.scan_project("proj")
    assert len(changes) >= 1
    assert changes[0].project_id == "proj"


def test_score_significance(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    watcher = GitWatcher(ledger, tasks, {})

    change = GitChange(
        project_id="proj", commit_hash="abc", commit_message="fix: critical bug",
        author="test", timestamp="2024-01-01", changed_files=["a.py", "b.py"],
        diff_stat="",
    )
    score = watcher.score_significance(change)
    assert score >= 0.3


def test_should_analyze_threshold(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    watcher = GitWatcher(ledger, tasks, {})
    change = GitChange(
        project_id="proj", commit_hash="abc", commit_message="fix: security vulnerability",
        author="test", timestamp="2024-01-01", changed_files=["a.py"],
        diff_stat="", significance=0.8,
    )
    assert watcher.should_analyze(change, threshold=0.5) is True
    assert watcher.should_analyze(change, threshold=0.9) is False


def test_create_analysis_task(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    tasks = TaskStore(str(tmp_path))
    ledger.add_project(Project(id="proj", name="test", repo="", local_path=str(tmp_path)))
    watcher = GitWatcher(ledger, tasks, {})

    change = GitChange(
        project_id="proj", commit_hash="abc123", commit_message="feat: major refactor",
        author="test", timestamp="2024-01-01",
        changed_files=["a.py", "b.py", "c.py"], diff_stat="",
    )
    task = watcher.create_analysis_task(change)
    if task:
        assert task.goal.startswith("Analyze commit")
        assert task.project_id == "proj"


def test_brain_wires_watcher(tmp_path):
    """Verify Brain creates a GitWatcher and registers projects with local_path."""
    from drift.brain import Brain

    env_path = str(tmp_path / "env")
    os.makedirs(env_path)
    ledger = DriftLedger(env_path)
    proj_path = str(tmp_path / "myproject")
    os.makedirs(proj_path)
    ledger.add_project(Project(id="p1", name="MyProject", repo="", local_path=proj_path))

    brain = Brain(identity={"name": "test"}, env_path=env_path)
    brain.stream = MemoryStream(env_path)
    brain._init_stores()

    assert hasattr(brain, 'watcher')
    assert "p1" in brain.watcher.get_watched_projects()


def test_brain_watcher_creates_tasks_from_commits(tmp_path):
    """End-to-end: Brain scans repos with new commits and creates analysis tasks."""
    import subprocess
    from drift.brain import Brain

    env_path = str(tmp_path / "env")
    os.makedirs(env_path)

    proj_path = str(tmp_path / "project")
    os.makedirs(proj_path)
    subprocess.run(["git", "init"], cwd=proj_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=proj_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=proj_path, capture_output=True)

    # Create 6 files to trigger significance (>=5 files = +0.1, >=10 = +0.2)
    for i in range(6):
        Path(proj_path, f"file{i}.py").write_text(f"print('hello {i}')")
    subprocess.run(["git", "add", "."], cwd=proj_path, capture_output=True)
    # "Merge" prefix (+0.2) + "security" keyword (+0.3) + 6 files (+0.1) = 0.6
    subprocess.run(["git", "commit", "-m", "Merge security fixes and schema migration"], cwd=proj_path, capture_output=True)

    ledger = DriftLedger(env_path)
    ledger.add_project(Project(id="proj", name="test", repo="", local_path=proj_path))

    brain = Brain(identity={"name": "test"}, env_path=env_path)
    brain.stream = MemoryStream(env_path)
    brain._init_stores()

    assert hasattr(brain, 'watcher')
    assert "proj" in brain.watcher.get_watched_projects()

    # Manually scan — should produce at least one change
    changes = brain.watcher.scan_all()
    assert len(changes) >= 1

    # Create analysis tasks for significant changes
    tasks_created = 0
    for change in changes:
        if brain.watcher.should_analyze(change):
            task = brain.watcher.create_analysis_task(change)
            if task:
                tasks_created += 1

    # security + feat keywords + 6 files should exceed the 0.5 threshold
    assert tasks_created >= 1
