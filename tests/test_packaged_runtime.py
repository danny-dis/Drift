import json
import os
import subprocess
import sys
from pathlib import Path


def test_packaged_config_loads_without_source_checkout(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'drift'
    package = tmp_path / 'installed' / 'drift'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    for name in ['config.py', 'runtime_resources.py']:
        if (source / name).exists():
            (package / name).write_text((source / name).read_text(encoding='utf-8'), encoding='utf-8')
    resources = package / 'resources'
    resources.mkdir()
    (resources / 'config.yaml').write_text('provider: dmrx\nbase_url: http://127.0.0.1:47113/v1\nmodel: auto-free\n')
    working = tmp_path / 'user-work'
    working.mkdir()
    env = os.environ.copy()
    env['PYTHONPATH'] = str(package.parent)
    result = subprocess.run([sys.executable, '-c',
        'import json; from drift.config import config; print(json.dumps({"model": config["model"], "path": config["environment_path"]}))'],
        cwd=working, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    settings = json.loads(result.stdout)
    assert Path(settings['path']).is_relative_to(working)


def test_packaged_frontend_resource_resolution(tmp_path):
    from drift.runtime_resources import frontend_directory
    package = tmp_path / 'drift'
    (package / 'resources' / 'frontend').mkdir(parents=True)
    (package / 'resources' / 'frontend' / 'index.html').write_text('installed frontend')
    assert frontend_directory(package) == package / 'resources' / 'frontend'
