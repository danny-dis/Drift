"""Release resources must be complete and contain no local credentials or state."""

import json
from pathlib import Path
import tomllib

import pytest

from drift.release_build import prepare_resources


@pytest.fixture
def release_tree(tmp_path):
    (tmp_path / "drift").mkdir()
    (tmp_path / "config.yaml").write_text("provider: dmrx\napi_key: ''\n", encoding="utf-8")
    frontend = tmp_path / "frontend" / "dist"
    (frontend / "assets" / "nested").mkdir(parents=True)
    (frontend / "index.html").write_text('<script src="/assets/app.js"></script>', encoding="utf-8")
    (frontend / "assets" / "app.js").write_text("console.log('release')", encoding="utf-8")
    (frontend / "assets" / "nested" / "app.css").write_text("body{}", encoding="utf-8")
    return tmp_path


def test_prepare_copies_config_and_nested_frontend_only(release_tree):
    (release_tree / ".env").write_text("PRIVATE=not-for-release", encoding="utf-8")
    (release_tree / "environment").mkdir()
    (release_tree / "environment" / "memory.json").write_text("[]", encoding="utf-8")
    target = prepare_resources(release_tree)
    files = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert files == {"config.yaml", "frontend/index.html", "frontend/assets/app.js", "frontend/assets/nested/app.css"}
    assert (target / "config.yaml").read_bytes() == (release_tree / "config.yaml").read_bytes()


def test_prepare_replaces_stale_resources(release_tree):
    target = prepare_resources(release_tree)
    (target / "frontend" / "stale.js").write_text("old", encoding="utf-8")
    prepare_resources(release_tree)
    assert not (target / "frontend" / "stale.js").exists()


@pytest.mark.parametrize("credential", ["api_key", "ollama_api_key", "access_token", "password", "client_secret"])
def test_prepare_rejects_embedded_credentials(release_tree, credential):
    (release_tree / "config.yaml").write_text(f"nested:\n  {credential}: never-print-this\n", encoding="utf-8")
    with pytest.raises(ValueError, match="credential") as exc:
        prepare_resources(release_tree)
    assert "never-print-this" not in str(exc.value)
    assert not (release_tree / "drift" / "resources").exists()


@pytest.mark.parametrize("url", ["https://user:private@example.com/v1", "https://example.com/v1?api_key=private"])
def test_prepare_rejects_credentials_in_urls(release_tree, url):
    (release_tree / "config.yaml").write_text(f"base_url: '{url}'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="credential"):
        prepare_resources(release_tree)


@pytest.mark.parametrize("unexpected", [".env", "secret.txt", "assets/app.js.map"])
def test_prepare_rejects_unexpected_frontend_files(release_tree, unexpected):
    (release_tree / "frontend" / "dist" / unexpected).write_text("not-public", encoding="utf-8")
    with pytest.raises(ValueError, match="frontend"):
        prepare_resources(release_tree)


def test_prepare_requires_built_frontend(release_tree):
    (release_tree / "frontend" / "dist" / "index.html").unlink()
    with pytest.raises(FileNotFoundError, match="npm run build"):
        prepare_resources(release_tree)


def test_failed_validation_preserves_existing_resources(release_tree):
    target = prepare_resources(release_tree)
    before = (target / "config.yaml").read_bytes()
    (release_tree / "config.yaml").write_text("api_key: private\n", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_resources(release_tree)
    assert (target / "config.yaml").read_bytes() == before


def test_release_versions_and_recursive_package_data_agree():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == frontend["version"] == lock["version"] == lock["packages"][""]["version"] == "0.2.3"
    assert metadata["build-system"]["build-backend"] == "setuptools.build_meta"
    assert "resources/**/*" in metadata["tool"]["setuptools"]["package-data"]["drift"]
