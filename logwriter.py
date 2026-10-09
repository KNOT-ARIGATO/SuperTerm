"""Automatic log files: one file per connection, every line time-stamped."""
import os
import re
import time
from datetime import datetime

MAX_BYTES = 50 * 1024 * 1024        # start a new part file after 50 MB


def default_log_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "SuperTerm Logs")


def _safe(text):
    return re.sub(r"[^\w.@-]+", "_", text).strip("_")[:60] or "session"


class LogWriter:
    """Append-only text log. `label` is e.g. 'Serial COM7 @ 115200'."""

    def __init__(self, folder, label):
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.base = os.path.join(folder, f"{stamp}_{_safe(label)}")
        self.part = 1
        self.path = self.base + ".log"
        self._f = open(self.path, "a", encoding="utf-8", newline="\n")
        self._last_flush = time.monotonic()
        self.write(f"=== SuperTerm log · {label} · {datetime.now():%Y-%m-%d %H:%M:%S} ===", True)

    def write(self, text, is_sys=False):
        if self._f is None:
            return
        now = datetime.now()
        self._f.write(f"[{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d}] "
                      f"{'# ' if is_sys else ''}{text}\n")
        t = time.monotonic()
        if t - self._last_flush > 1.0:            # at most one disk flush per second
            self._f.flush()
            self._last_flush = t
            if self._f.tell() > MAX_BYTES:
                self._rotate()

    def _rotate(self):
        self._f.close()
        self.part += 1
        self.path = f"{self.base}_part{self.part}.log"
        self._f = open(self.path, "a", encoding="utf-8", newline="\n")

    def close(self):
        if self._f is not None:
            try:
                self.write("=== log closed ===", True)
                self._f.close()
            finally:
                self._f = None
