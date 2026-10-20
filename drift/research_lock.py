"""Bounded, reentrant research writer mutex with crash-safe OS ownership."""
import errno
import os
import threading
import time


class ResearchMutex:
    def __init__(self, root):
        self.path = os.path.join(root, '.research-writer.lock')
        self.thread_lock = threading.RLock()
        self.depth = 0
        self.stream = None

    def acquire(self):
        deadline = time.monotonic() + 10
        if not self.thread_lock.acquire(timeout=10):
            raise TimeoutError('Research writer is busy')
        if self.depth:
            self.depth += 1
            return
        stream = None
        try:
            stream = open(self.path, 'a+b')
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'\0')
                stream.flush()
            while True:
                stream.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Research writer is busy') from error
                    time.sleep(min(.02, remaining))
            self.stream = stream
            self.depth = 1
        except BaseException:
            if stream is not None:
                stream.close()
            self.thread_lock.release()
            raise

    def release(self):
        # Validate thread ownership before changing the shared recursion depth.
        if not self.thread_lock._is_owned():
            raise RuntimeError('Research writer lock is not owned by this thread')
        self.depth -= 1
        try:
            if self.depth == 0:
                self.stream.close()  # Closing releases the OS lock, including after crashes.
                self.stream = None
        finally:
            self.thread_lock.release()
