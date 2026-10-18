import os
from pathlib import Path
import subprocess

import pytest

from drift.organism import git_diff_summary, git_snapshot
from drift.watcher import _run_git


def git(root, *args):
    return subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.email', 'audit@example.invalid')
    git(tmp_path, 'config', 'user.name', 'Regression')
    (tmp_path / 'note.txt').write_text('first\n', encoding='utf-8')
    git(tmp_path, 'add', 'note.txt')
    git(tmp_path, 'commit', '-qm', 'initial')
    return tmp_path


def hook(root, marker):
    script = root / 'probe.sh'
    script.write_text('#!/bin/sh\nprintf executed > "' + marker.as_posix()
                      + '"\ncat\n', encoding='utf-8')
    script.chmod(0o700)
    return 'sh "' + script.as_posix() + '"'


@pytest.mark.parametrize('inspect', [git_snapshot, lambda root: _run_git(root, 'status', '--porcelain')])
def test_inspection_never_executes_fsmonitor(repository, inspect):
    marker = repository / 'executed.txt'
    git(repository, 'config', 'core.fsmonitor', hook(repository, marker))
    inspect(str(repository))
    assert not marker.exists(), 'read-only inspection executed a repository command'


def test_inspection_never_executes_clean_filter(repository):
    marker = repository / 'executed.txt'
    git(repository, 'config', 'filter.audit.clean', hook(repository, marker))
    git(repository, 'config', 'filter.audit.required', 'true')
    (repository / '.gitattributes').write_text('note.txt filter=audit\n', encoding='utf-8')
    (repository / 'note.txt').write_text('other\n', encoding='utf-8')
    snapshot = git_snapshot(str(repository))
    assert not marker.exists(), 'status executed a configured clean filter'
    assert snapshot['dirty']


def test_inspection_never_executes_external_diff_or_textconv(repository):
    marker = repository / 'executed.txt'
    command = hook(repository, marker)
    git(repository, 'config', 'diff.external', command)
    git(repository, 'config', 'diff.audit.textconv', command)
    (repository / '.gitattributes').write_text('note.txt diff=audit\n', encoding='utf-8')
    (repository / 'note.txt').write_text('changed\n', encoding='utf-8')
    _run_git(str(repository), 'diff', 'HEAD')
    git_diff_summary(str(repository))
    assert not marker.exists(), 'diff inspection executed an external program'


def test_parent_status_does_not_run_submodule_filters_but_keeps_gitlink_changes(repository, tmp_path):
    seed = tmp_path / 'seed'
    seed.mkdir()
    git(seed, 'init', '-q')
    git(seed, 'config', 'user.email', 'audit@example.invalid')
    git(seed, 'config', 'user.name', 'Regression')
    (seed / 'note.txt').write_text('one\n', encoding='utf-8')
    git(seed, 'add', 'note.txt')
    git(seed, 'commit', '-qm', 'initial')
    git(repository, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(seed), 'nested')
    git(repository, 'commit', '-qm', 'submodule')
    nested = repository / 'nested'
    marker = repository / 'nested-executed.txt'
    git(nested, 'config', 'filter.nested.clean', hook(repository, marker))
    git(nested, 'config', 'filter.nested.required', 'true')
    (nested / '.gitattributes').write_text('note.txt filter=nested\n', encoding='utf-8')
    (nested / 'note.txt').write_text('two\n', encoding='utf-8')
    stamp = (nested / 'note.txt').stat().st_mtime + 2
    os.utime(nested / 'note.txt', (stamp, stamp))
    git_snapshot(str(repository))
    assert not marker.exists(), 'parent inspection executed a submodule filter'
    git(nested, '-c', 'user.email=audit@example.invalid', '-c', 'user.name=Regression',
        '-c', 'filter.nested.clean=', '-c', 'filter.nested.required=false',
        'commit', '--allow-empty', '-qm', 'new submodule commit')
    assert 'nested' in git_snapshot(str(repository))['changed_files']
    assert not marker.exists()


def test_watcher_does_not_execute_implicit_signature_verifier(repository):
    from drift.organism import DriftLedger, Project
    from drift.task import TaskStore
    from drift.watcher import GitWatcher
    raw = git(repository, 'cat-file', 'commit', 'HEAD').replace('\r\n', '\n')
    header, body = raw.split('\n\n', 1)
    signed = header + '\ngpgsig -----BEGIN PGP SIGNATURE-----\n dummy\n -----END PGP SIGNATURE-----\n\n' + body
    created = subprocess.run(['git', 'hash-object', '-t', 'commit', '-w', '--stdin'],
                             cwd=repository, input=signed.encode('utf-8'), capture_output=True, check=True)
    git(repository, 'update-ref', 'HEAD', created.stdout.decode().strip())
    marker = repository / 'signature-executed.txt'
    script = repository / 'verifier.sh'
    script.write_text('#!/bin/sh\nprintf executed > "' + marker.as_posix() + '"\nexit 1\n', encoding='utf-8')
    script.chmod(0o700)
    git(repository, 'config', 'log.showSignature', 'true')
    git(repository, 'config', 'gpg.program', str(script))
    ledger = DriftLedger(str(repository / 'state'))
    ledger.add_project(Project('probe', 'Probe', '', str(repository)))
    watcher = GitWatcher(ledger, TaskStore(str(repository / 'state')), {'shell_enabled': False})
    changes = watcher.scan_project('probe', str(repository))
    assert changes
    assert not marker.exists(), 'watcher executed a repository signature verifier'
