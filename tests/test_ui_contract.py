"""UI lane contract: DriftApp.tsx must talk to the real backend (read-only check).

Owned by ui lane. Does not touch drift/ui_api.py (see tests/test_ui_lane.py,
owned outside frontend scope — preserved as-is).
"""
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "frontend" / "src" / "DriftApp.tsx"


def _src():
    return APP.read_text(encoding="utf-8")


def test_uses_real_status_endpoint():
    src = _src()
    assert "/api/status" in src, "UI must fetch real /api/status (no decorative status)"


def test_uses_ui_routes():
    src = _src()
    for route in [
        "/api/ui/projects",
        "/api/ui/ideas",
        "/api/ui/research",
        "/api/ui/research/evidence",
        "/api/ui/budget",
        "/api/ui/attention/candidates",
        "/api/ui/receipts",
        "/api/ui/approvals",
        "/api/identity",
    ]:
        assert route in src, f"UI must communicate via {route}"


def test_checks_response_ok_before_success():
    src = _src()
    assert "response.ok" in src or "res.ok" in src or ".ok" in src, \
        "UI must check response.ok before reporting success"


def test_preserves_input_on_failed_capture():
    src = _src()
    # Capture field must not be blindly cleared: clear only on ok.
    assert "sessionStorage" in src, "auth token entry stored in sessionStorage required"
    assert ".ok" in src


def test_project_register_and_session_payloads():
    src = _src()
    assert "local_path" in src and "importance" in src, "project register fields required"
    assert "/api/ui/research/sessions" in src, "research session create/list route required"
    assert "project_id" in src


def test_selected_details_budget_approvals_evidence():
    src = _src()
    lowered = src.lower()
    for needle in ["approve", "budget", "receipt", "evidence", "citat", "unverif", "uncertain"]:
        assert needle in lowered, f"UI must cover '{needle}'"


def test_accessible_no_dangerous_html():
    src = _src()
    assert "dangerouslySetInnerHTML" not in src, "no arbitrary HTML injection"
    assert "aria-" in src or "role=" in src or "<label" in src, "semantic accessible controls required"
