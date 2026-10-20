"""Additional ownership checks for research lock crash/reentrancy behavior."""
import subprocess
import sys
import threading
import pytest
from drift.research_lock import ResearchMutex


def test_lock_is_reentrant_and_rejects_foreign_thread_release(tmp_path):
    lock = ResearchMutex(str(tmp_path))
    lock.acquire()
    lock.acquire()
    errors = []
    def wrong_owner():
        try:
            lock.release()
        except RuntimeError:
            errors.append('rejected')
    thread = threading.Thread(target=wrong_owner)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert errors == ['rejected']
    lock.release()
    lock.release()
    lock.acquire()
    lock.release()


def test_process_exit_releases_lock_without_stale_directory_cleanup(tmp_path):
    code = """
import os, sys
from drift.research_lock import ResearchMutex
lock = ResearchMutex(sys.argv[1])
lock.acquire()
os._exit(0)
"""
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    lock = ResearchMutex(str(tmp_path))
    lock.acquire()
    lock.release()
