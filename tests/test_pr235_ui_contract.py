"""Read-only UI contracts, supplemented by real browser release checks."""
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "DriftApp.tsx"


def test_dashboard_loads_real_decision_summary_and_provenance():
    text = APP.read_text(encoding="utf-8")
    assert 'get("/api/ui/decisions")' in text
    for field in ("query_history", "tools", "scripts", "file_changes", "report_attempts", "repair_context"):
        assert f"sessionDetail.{field}" in text
    assert "keyword gates are not semantic judgments" in text


def test_repair_is_explicit_and_uses_same_session():
    text = APP.read_text(encoding="utf-8")
    assert '/api/ui/research/sessions/${id}/resume' in text
    assert 'sessionDetail.state === "needs_review"' in text
    assert 'Resume same task for repair' in text
    assert 'dangerouslySetInnerHTML' not in text
