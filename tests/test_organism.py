from drift.organism import DriftEvent, DriftLedger, Project, git_snapshot


def test_ledger_builds_mind_map(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    idea = ledger.add_idea("Use a graph for project intelligence", ["knowledge graph"])
    ledger.add_project(Project(id="athena", name="ATHENA", repo="danny-dis/ATHENA"))
    ledger.add_event(DriftEvent(kind="observation", source="test", summary="new architecture note", related_projects=["athena"], related_ideas=[idea.id]))
    assert idea.id.startswith("idea-")
    assert any(n["kind"] == "concept" for n in ledger.data["mind_map"]["nodes"])
    assert ledger.data["events"][-1]["summary"] == "new architecture note"


def test_git_snapshot_is_deterministic(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    snapshot = git_snapshot(str(tmp_path))
    assert snapshot["branch"] in ("", "master", "main")
    assert snapshot["dirty"] is False
