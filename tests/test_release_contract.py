from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_installs_python_test_dependencies_and_uses_locked_frontend_install():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in ci
    assert "python -m pip install -e '.[test]'" in ci
    assert "python -m pytest -p no:cacheprovider -q" in ci
    assert "npm ci && npm run build" in ci


def test_frontend_dev_proxy_matches_runtime_default_port():
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    config = (ROOT / "drift" / "config.py").read_text(encoding="utf-8")
    assert 'port: 5173' in vite
    assert 'http://localhost:47116' in vite
    assert 'ws://localhost:47116' in vite
    assert '"47116"' in config
