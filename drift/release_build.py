"""Stage public release resources and verify wheels outside the source checkout."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, urlsplit
import venv
import zipfile

import yaml

PUBLIC_EXTENSIONS = {".html", ".js", ".css", ".json", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".wasm"}


def _credential_key(key: str) -> bool:
    key = key.lower().replace("-", "_")
    return key in {"key", "secret", "token", "password", "authorization"} or key.endswith(("_api_key", "api_key", "_token", "_secret", "_password"))


def _validate_config(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _credential_key(str(key)) and item:
                raise ValueError("Release config contains a non-empty credential field")
            _validate_config(item)
    elif isinstance(value, list):
        for item in value:
            _validate_config(item)
    elif isinstance(value, str) and "://" in value:
        url = urlsplit(value)
        if url.username or url.password or any(_credential_key(k) and v for k, v in parse_qsl(url.query)):
            raise ValueError("Release config contains URL credentials")


def prepare_resources(root: Path) -> Path:
    """Copy only credential-free defaults and a built public frontend."""
    root = Path(root).resolve()
    config = root / "config.yaml"
    frontend = root / "frontend" / "dist"
    if config.is_symlink() or frontend.is_symlink():
        raise ValueError("Release sources must not be symlinks")
    parsed = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Release config must be a mapping")
    _validate_config(parsed)
    if not (frontend / "index.html").is_file():
        raise FileNotFoundError("Build the frontend first: cd frontend && npm ci && npm run build")
    entries = sorted(frontend.rglob("*"))
    for entry in entries:
        relative = entry.relative_to(frontend)
        if entry.is_symlink() or any(part.startswith(".") for part in relative.parts):
            raise ValueError("Release frontend contains a symlink or hidden file")
        if entry.is_file() and entry.suffix.lower() not in PUBLIC_EXTENSIONS:
            raise ValueError("Release frontend contains a non-public file type")
    if not any(entry.is_file() and entry.suffix == ".js" for entry in entries):
        raise ValueError("Release frontend must contain built JavaScript")
    target = root / "drift" / "resources"
    if target.is_symlink():
        raise ValueError("Release resources must not be a symlink")
    with tempfile.TemporaryDirectory(prefix="drift-resources-") as temporary:
        staged = Path(temporary) / "resources"
        staged.mkdir()
        shutil.copyfile(config, staged / "config.yaml")
        shutil.copytree(frontend, staged / "frontend")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(staged, target)
    return target


SMOKE_CODE = r'''
import asyncio
from importlib.metadata import version
from pathlib import Path
import re
import sys
import httpx
import drift
from drift.config import CONFIG_PATH, load_config
from drift.server import create_app

expected = sys.argv[1]
assert version("drift") == expected, version("drift")
package = Path(drift.__file__).resolve().parent
assert package.is_relative_to(Path(sys.prefix).resolve()), package
assert Path(CONFIG_PATH).resolve().is_relative_to(package), CONFIG_PATH
assert isinstance(load_config(), dict)
frontend = package / "resources" / "frontend"
index = (frontend / "index.html").read_bytes()

async def smoke():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app({})), base_url="http://127.0.0.1") as client:
        response = await client.get("/")
        assert response.status_code == 200, response.status_code
        assert response.content == index, "Root did not serve the packaged frontend"
        scripts = re.findall(r'<script\b[^>]*\bsrc=["\']([^"\']+\.js)["\']', response.text)
        assert scripts, "Packaged HTML has no JavaScript script"
        for script in scripts:
            asset = await client.get(script)
            assert asset.status_code == 200, (script, asset.status_code)
            assert asset.content == (frontend / script.lstrip("/")).read_bytes(), script
    print(f"Installed Drift {expected}: packaged config, root HTML and {len(scripts)} JavaScript assets OK")

asyncio.run(smoke())
'''


def smoke_wheel(wheel: Path, expected_version: str) -> None:
    """Install all dependencies into a fresh venv; never import from the checkout."""
    wheel = Path(wheel).resolve(strict=True)
    if wheel.suffix != ".whl":
        raise ValueError("Smoke verification requires a wheel")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("DRIFT_") and key not in {"PYTHONPATH", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_API_KEY"}}
    with tempfile.TemporaryDirectory(prefix="drift-wheel-smoke-") as directory:
        temporary = Path(directory)
        venv.EnvBuilder(with_pip=True).create(temporary / "venv")
        python = temporary / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=temporary, env=environment, check=True)
        subprocess.run([str(python), "-I", "-c", SMOKE_CODE, expected_version], cwd=temporary, env=environment, check=True)


def release_assets(root: Path, output: Path, version: str) -> None:
    """Create a frontend archive and checksum manifest beside Python artifacts."""
    frontend = Path(root) / "drift" / "resources" / "frontend"
    output = Path(output)
    if not (frontend / "index.html").is_file():
        raise FileNotFoundError("Prepare release resources before creating assets")
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / f"drift-frontend-{version}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(frontend.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(frontend).as_posix())
    artifacts = sorted(p for p in output.iterdir() if p.name.endswith((".whl", ".tar.gz", ".zip")))
    checksums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in artifacts]
    (output / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--smoke", type=Path, help="Install and verify this wheel in an isolated temporary venv")
    parser.add_argument("--assets", type=Path, help="Create frontend archive and checksums in this artifact directory")
    parser.add_argument("--expect-version", default="0.2.1")
    args = parser.parse_args()
    if args.smoke:
        smoke_wheel(args.smoke, args.expect_version)
    elif args.assets:
        release_assets(args.root, args.assets, args.expect_version)
    else:
        print(f"Prepared release resources: {prepare_resources(args.root)}")


if __name__ == "__main__":
    main()
