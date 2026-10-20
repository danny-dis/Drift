from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_has_page_heading_and_accessible_project_metadata():
    app = (ROOT / "frontend/src/DriftApp.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/drift.css").read_text(encoding="utf-8")
    assert '<h1 className="brand">DRIFT</h1>' in app
    assert '<h2 className="panel-title">Research</h2>' in app
    assert '.pad .project small{font-size:12px;color:#aeb6c4}' in css
