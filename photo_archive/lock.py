"""Build lock — prevents concurrent execution."""

import logging
import os
import time

logger = logging.getLogger(__name__)


class BuildLock:
    """Simple file-based lock for NAS-safe concurrent execution prevention."""

    def __init__(self, lock_dir: str):
        self.lock_path = os.path.join(lock_dir, "build.lock")
        self._acquired = False

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if successful."""
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)

        if os.path.exists(self.lock_path):
            # Check if stale (older than 2 hours)
            try:
                age = time.time() - os.path.getmtime(self.lock_path)
                if age > 7200:
                    logger.warning("Removing stale lock (%.0f seconds old)", age)
                    os.remove(self.lock_path)
                else:
                    logger.error(
                        "Build lock exists (%s). Another build may be running. "
                        "If not, delete the lock file manually.",
                        self.lock_path,
                    )
                    return False
            except OSError:
                return False

        try:
            with open(self.lock_path, "w", encoding="utf-8") as f:
                f.write(f"pid={os.getpid()}\ntime={time.time()}\n")
            self._acquired = True
            return True
        except OSError as exc:
            logger.error("Cannot create lock: %s", exc)
            return False

    def release(self):
        if self._acquired and os.path.exists(self.lock_path):
            try:
                os.remove(self.lock_path)
            except OSError:
                pass
            self._acquired = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Cannot acquire build lock")
        return self

    def __exit__(self, *args):
        self.release()
