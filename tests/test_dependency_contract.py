from pathlib import Path
import tomllib


def test_direct_httpx_import_is_declared_and_sdk_major_is_bounded():
    metadata=tomllib.loads((Path(__file__).resolve().parents[1]/'pyproject.toml').read_text())
    deps=metadata['project']['dependencies']
    assert any(d.startswith('httpx>=') for d in deps)
    assert any(d.startswith('openai>=') and '<3' in d for d in deps)
