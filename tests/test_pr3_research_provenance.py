"""PR3 provenance, checkpoint, and bounded-repair contracts."""

import json

import pytest

from drift.research import ResearchStore


def test_resume_preserves_evidence_and_has_deterministic_action(tmp_path):
    store = ResearchStore(str(tmp_path))
    session = store.start("compare crab habitats")
    source = store.add_source(session["id"], "https://example.com/crab", "A retained source excerpt.")
    store.record_step(session["id"], "researching", "query", {"text": "crab habitat sources"})

    resumed = ResearchStore(str(tmp_path)).resume(session["id"])
    assert resumed["sources"][0]["id"] == source["id"]
    assert resumed["query_history"][-1]["text"] == "crab habitat sources"
    assert resumed["phase"] == "researching"
    assert resumed["next_action"] == "research"
    assert resumed["checkpoint"]["rev"] == resumed["rev"]


def test_record_step_retains_bounded_tool_script_file_and_note_lineage(tmp_path):
    store = ResearchStore(str(tmp_path))
    session = store.start("inspect the registered project")
    sid = session["id"]
    store.record_step(sid, "researching", "tool", {
        "name": "fetch_url", "status": "ok", "url": "https://example.com/a",
        "result": "real fetch result", "broken_links": [],
    })
    store.record_step(sid, "synthesizing", "note", {"text": "Compare the source dates."})
    store.record_step(sid, "writing", "script", {"path": "analysis/check.py", "content": "print('review')"})
    store.record_step(sid, "verifying", "file_change", {"path": "../outside.txt", "action": "write"})
    got = store.get(sid)
    assert got["tools"][-1]["name"] == "fetch_url"
    assert got["tools"][-1]["broken_links"] == []
    assert got["notes"][-1]["text"] == "Compare the source dates."
    assert got["scripts"][-1]["path"] == "analysis/check.py"
    assert got["file_changes"][-1]["accepted"] is False
    assert "escapes" in got["file_changes"][-1]["error"]
    assert not (tmp_path.parent / "outside.txt").exists()


def test_invalid_report_attempts_and_repair_context_survive_success(tmp_path):
    store = ResearchStore(str(tmp_path))
    session = store.start("crab molt")
    source = store.add_source(session["id"], "https://example.com/molt", "Source about crab molting.")
    invalid = {"findings": ["unsupported claim"], "citations": [{"source_id": "missing"}]}
    rejected = store.finish(session["id"], invalid)
    assert rejected["state"] == "needs_review"
    assert rejected["report_attempts"][-1]["report"] == invalid
    assert rejected["repair_context"][-1]["errors"]

    completed = store.finish(session["id"], {
        "findings": ["A report finding"],
        "citations": [{"source_id": source["id"], "note": "source"}],
    })
    reopened = ResearchStore(str(tmp_path)).get(session["id"])
    assert completed["state"] == "complete"
    assert len(reopened["report_attempts"]) == 2
    assert reopened["report_attempts"][0]["report"] == invalid
    assert reopened["sources"][0]["id"] == source["id"]
    assert reopened["verified"] is False


def test_candidate_overlap_is_labeled_lexical_and_can_be_disabled(tmp_path, monkeypatch):
    from drift.config import config

    store = ResearchStore(str(tmp_path))
    session = store.start("compare crab molting vs fish growth and evaluate which helps survival?")
    src = store.add_source(session["id"], "https://example.com/a", "Crab molting survival growth strategy.")
    done = store.finish(session["id"], {
        "findings": ["Crab molting is relevant."],
        "citations": [{"source_id": src["id"]}],
    })
    assert "lexical_coverage" in done["coverage"]["hypotheses"][0]
    assert "evidential_support" not in done["coverage"]["hypotheses"][0]
    assert done["candidates"][0]["support"] == done["candidates"][0]["lexical_coverage"]

    monkeypatch.setitem(config, "research_candidates_enabled", False)
    without = ResearchStore(str(tmp_path / "disabled")).start(
        "compare crab molting vs fish growth and evaluate which helps survival?")
    assert without["candidates"] == []
    assert without["outline"] == []


def test_export_includes_failed_reports_and_lineage(tmp_path):
    store = ResearchStore(str(tmp_path))
    session = store.start("query export")
    store.record_step(session["id"], "researching", "query", {"text": "follow-up query"})
    store.finish(session["id"], {"findings": ["bad"], "citations": [{"source_id": "missing"}]})
    exported = store.export_markdown(session["id"])
    assert "follow-up query" in exported
    assert "Report attempts" in exported
    assert "unknown source" in exported
    disk = json.loads((tmp_path / "sessions" / f"{session['id']}.json").read_text(encoding="utf-8"))
    assert disk["phase"] == "verifying"
    assert disk["report"] is None
