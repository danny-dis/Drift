"""Read and atomically publish a registered project's unlinked drift.md."""
import os
from pathlib import Path
import stat
import tempfile


def _checked_stat(target):
    try:
        info = target.lstat()
    except FileNotFoundError:
        return None
    _check_file(info)
    if target.resolve().parent != target.parent:
        raise ValueError('drift.md must remain inside the registered project')
    return info


def _check_file(info):
    reparse = getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or reparse:
        raise ValueError('drift.md must be a regular, unlinked project file')


def read_document(root, limit=-1):
    target = Path(root).resolve() / 'drift.md'
    expected = _checked_stat(target)
    if expected is None:
        return ''
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(target, flags)
    with os.fdopen(descriptor, 'r', encoding='utf-8', errors='replace') as stream:
        opened = os.fstat(stream.fileno())
        _check_file(opened)
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError('drift.md changed while opening; retry after inspection')
        return stream.read(limit)


def write_document(root, text):
    target = Path(root).resolve() / 'drift.md'
    _checked_stat(target)
    descriptor, temporary = tempfile.mkstemp(prefix='.drift-md-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _checked_stat(target)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
