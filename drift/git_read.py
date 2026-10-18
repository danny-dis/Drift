"""Bounded Git inspection without repository-configured executable helpers."""
import os
from pathlib import Path
import subprocess


def read_git(path: str, *args: str) -> str:
    base = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
            '-c', 'core.hooksPath=' + os.devnull, '-c', 'log.showSignature=false',
            '-c', 'diff.ignoreSubmodules=dirty', '-c', 'diff.submodule=short',
            '-c', 'status.submoduleSummary=false']
    try:
        filters = subprocess.run(
            [*base, 'config', '--null', '--name-only', '--get-regexp',
             r'^filter\..*\.(clean|smudge|process|required)$'],
            cwd=Path(path), capture_output=True, text=True, timeout=30,
        )
        if filters.returncode not in (0, 1):
            return ''
        drivers = {key.rsplit('.', 1)[0] for key in filters.stdout.split('\0') if key}
        for driver in sorted(drivers):
            for setting in ('clean', 'smudge', 'process'):
                base.extend(['-c', f'{driver}.{setting}='])
            base.extend(['-c', f'{driver}.required=false'])
        if args and args[0] in ('diff', 'diff-tree', 'log', 'show'):
            args = (args[0], '--no-ext-diff', '--no-textconv', *args[1:])
        if args and args[0] == 'status':
            # ponytail: ignore nested worktree dirtiness; register submodules separately to inspect it safely.
            args = (args[0], '--ignore-submodules=dirty', *args[1:])
        result = subprocess.run([*base, *args], cwd=Path(path),
                                capture_output=True, text=True, timeout=30)
        return result.stdout.rstrip('\r\n') if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''
