"""Tests for drift/task.py — durable task state management."""
import json
from pathlib import Path

import pytest

from drift.task import PHASES, Task, TaskStore, can_transition


def test_create_task_assigns_unique_ids(tmp_path):
    store = TaskStore(str(tmp_path))
    t1 = store.create_task("goal1", "obj1")
    t2 = store.create_task("goal2", "obj2")
    t3 = store.create_task("goal3", "obj3")
    assert t1.id == "task-000000"
    assert t2.id == "task-000001"
    assert t3.id == "task-000002"


def test_get_next_task_highest_priority(tmp_path):
    store = TaskStore(str(tmp_path))
    store.create_task("low", "low", priority=0.2)
    store.create_task("high", "high", priority=0.9)
    store.create_task("mid", "mid", priority=0.5)
    task = store.get_next_task()
    assert task is not None
    assert task.goal == "high"


def test_get_next_task_skips_complete_and_blocked(tmp_path):
    store = TaskStore(str(tmp_path))
    t1 = store.create_task("do", "do", priority=0.9)
    t2 = store.create_task("done", "done", priority=0.5)
    t3 = store.create_task("blocked", "blocked", priority=0.3)
    # Transition t2 through valid phases to complete
    store.update_task(t2.id, phase="understand")
    store.update_task(t2.id, phase="connect")
    store.update_task(t2.id, phase="research")
    store.update_task(t2.id, phase="verify")
    store.update_task(t2.id, phase="synthesize")
    store.update_task(t2.id, phase="qualify")
    store.update_task(t2.id, phase="monitor")
    store.update_task(t2.id, phase="complete", status="complete")
    store.update_task(t3.id, phase="blocked", status="blocked")
    task = store.get_next_task()
    assert task is not None
    assert task.id == t1.id


def test_can_transition_forward():
    t = Task(id="t1", goal="g", objective="o", phase="capture")
    assert can_transition(t, "understand")
    assert can_transition(t, "blocked")


def test_can_transition_blocked():
    t = Task(id="t1", goal="g", objective="o", phase="blocked", _prev_phase="research")
    assert can_transition(t, "research")
    assert not can_transition(t, "understand")


def test_can_transition_rejects_jumps():
    t = Task(id="t1", goal="g", objective="o", phase="capture")
    assert not can_transition(t, "research")
    assert not can_transition(t, "complete")


def test_update_task_auto_timestamp(tmp_path):
    store = TaskStore(str(tmp_path))
    t = store.create_task("goal", "obj")
    old_ts = t.updated_at
    store.update_task(t.id, progress=0.5)
    updated = store.get_task(t.id)
    assert updated.updated_at >= old_ts
    assert updated.progress == 0.5


def test_update_task_rejects_bad_phase(tmp_path):
    store = TaskStore(str(tmp_path))
    t = store.create_task("goal", "obj")
    with pytest.raises(ValueError):
        store.update_task(t.id, phase="complete")


def test_task_resumes_after_blocked(tmp_path):
    store = TaskStore(str(tmp_path))
    t = store.create_task("goal", "obj")
    store.update_task(t.id, phase="understand")
    store.update_task(t.id, phase="connect")
    store.update_task(t.id, phase="research")
    store.update_task(t.id, phase="blocked")
    t2 = store.get_task(t.id)
    assert can_transition(t2, "research")


def test_save_and_load_roundtrip(tmp_path):
    store = TaskStore(str(tmp_path))
    store.create_task("goal1", "obj1", project_id="proj-1", priority=0.7)
    store.create_task("goal2", "obj2", project_id="proj-2", priority=0.3)
    store2 = TaskStore(str(tmp_path))
    assert len(store2.list_tasks()) == 2
    tasks = store2.list_tasks()
    assert tasks[0].goal == "goal1"


def test_reset_attempts(tmp_path):
    store = TaskStore(str(tmp_path))
    t = store.create_task("goal", "obj")
    store.update_task(t.id, attempt_count=5)
    store.reset_attempts(t.id)
    assert store.get_task(t.id).attempt_count == 0


def test_list_tasks_filtering(tmp_path):
    store = TaskStore(str(tmp_path))
    store.create_task("goal1", "obj1", project_id="p1", priority=0.9)
    store.create_task("goal2", "obj2", project_id="p2", priority=0.8)
    store.create_task("goal3", "obj3", project_id="p1", priority=0.7)
    store.update_task(store.list_tasks()[2].id, status="pending")
    p1_tasks = store.list_tasks(project_id="p1")
    assert len(p1_tasks) == 2
    pending = store.list_tasks(status="pending")
    assert len(pending) == 3
