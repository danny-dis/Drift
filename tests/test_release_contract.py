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


def test_release_docs_describe_bounded_local_workbench_truthfully():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "shell execution is disabled unless explicitly" in readme
    assert "shell_enabled: true" in readme
    assert "free-only" in readme
    assert "localhost:47116" in readme
    assert "citations" in readme and "not" in readme
    assert "registered" in readme and "drift.md" in readme
    assert "does not silently modify source code" in readme
    assert "fully complete" not in readme
    assert "security-certified" not in readme
    assert "tests pass" not in readme
