"""Light test sequences (no GUI imports).

A sequence is a list of steps:  send a command → wait for an expected text in
the device output → PASS / FAIL (timeout).  The UI feeds received lines with
feed_line() and calls tick() regularly; the runner calls send(text) itself.

Expect syntax
    OK              case-insensitive substring
    re:^ver \\d+    regular expression (case-insensitive)
    (empty)         no check — just send and wait `timeout` seconds
"""
import copy
import csv
import json
import os
import re
import time
from datetime import datetime


def make_step(send="", expect="", timeout=5.0, on_fail="stop"):
    return {"send": send, "expect": expect, "timeout": float(timeout), "on_fail": on_fail}


def _matcher(expect):
    expect = (expect or "").strip()
    if not expect:
        return None
    if expect.lower().startswith("re:"):
        rx = re.compile(expect[3:].strip(), re.I)
        return lambda line: bool(rx.search(line))
    low = expect.lower()
    return lambda line: low in line.lower()


class Runner:
    """State machine for one run of a sequence."""

    def __init__(self, steps, send, now=None):
        self.steps = [dict(s) for s in steps]
        self.send = send                      # callable(text) -> bool
        self.results = []                     # dicts: step, status, line, seconds
        self.i = -1
        self.done = False
        self.stopped = False
        self._t0 = None
        self._match = None
        self._start_step(now if now is not None else time.monotonic())

    def _start_step(self, now):
        self.i += 1
        if self.i >= len(self.steps):
            self.done = True
            return
        s = self.steps[self.i]
        try:
            self._match = _matcher(s.get("expect"))
        except re.error as e:
            self._finish("FAIL", f"bad pattern: {e}", now)
            return
        self._t0 = now
        if s.get("send"):
            if not self.send(s["send"]):
                self._finish("FAIL", "send failed (not connected?)", now)

    def _finish(self, status, line, now):
        s = self.steps[self.i]
        self.results.append({"step": self.i + 1, "send": s.get("send", ""), "expect": s.get("expect", ""),
                             "status": status, "line": line, "seconds": round(now - (self._t0 or now), 2)})
        if status != "PASS" and s.get("on_fail", "stop") == "stop":
            self.done = True
            return
        self._start_step(now)

    def feed_line(self, line, now=None):
        if self.done or self._match is None or len(self.results) > self.i:
            return
        if self._match(line):
            self._finish("PASS", line, now if now is not None else time.monotonic())

    def tick(self, now=None):
        if self.done:
            return
        now = now if now is not None else time.monotonic()
        s = self.steps[self.i]
        if now - self._t0 >= float(s.get("timeout") or 0):
            if self._match is None:
                self._finish("PASS", "(sent, no check)", now)
            else:
                self._finish("FAIL", "timeout — expected text not seen", now)

    def stop(self, now=None):
        if not self.done:
            self.stopped = True
            self._finish_stopped(now if now is not None else time.monotonic())

    def _finish_stopped(self, now):
        s = self.steps[self.i]
        self.results.append({"step": self.i + 1, "send": s.get("send", ""), "expect": s.get("expect", ""),
                             "status": "STOPPED", "line": "", "seconds": round(now - (self._t0 or now), 2)})
        self.done = True

    @property
    def current(self):
        return self.i

    @property
    def passed(self):
        return self.done and not self.stopped and len(self.results) == len(self.steps) \
            and all(r["status"] == "PASS" for r in self.results)

    def summary(self):
        ok = sum(r["status"] == "PASS" for r in self.results)
        return {"total": len(self.steps), "passed": ok, "failed": len(self.results) - ok,
                "result": "PASS" if self.passed else ("STOPPED" if self.stopped else "FAIL")}


def append_csv(path, sequence_name, unit, runner, connection=""):
    """One row per step; creates the file with a header when new."""
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overall = runner.summary()["result"]
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "sequence", "unit", "connection", "overall", "step",
                        "send", "expect", "result", "seconds", "matched line"])
        for r in runner.results:
            w.writerow([stamp, sequence_name, unit, connection, overall, r["step"],
                        r["send"], r["expect"], r["status"], r["seconds"], r["line"]])


class SequenceStore:
    """Saved sequences: [{"name": str, "steps": [step, …]}] in a JSON file."""

    def __init__(self, path):
        self.path = path
        self.items = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for s in data.get("sequences", []):
                steps = [make_step(x.get("send", ""), x.get("expect", ""), x.get("timeout", 5),
                                   x.get("on_fail", "stop")) for x in s.get("steps", []) if isinstance(x, dict)]
                self.items.append({"name": str(s.get("name", "Sequence")), "steps": steps})
        except (OSError, ValueError, AttributeError, TypeError):
            pass

    def names(self):
        return [s["name"] for s in self.items]

    def get(self, i):
        return copy.deepcopy(self.items[i])

    def put(self, i, seq):
        if 0 <= i < len(self.items):
            self.items[i] = copy.deepcopy(seq)
        else:
            self.items.append(copy.deepcopy(seq))
        return self.save()

    def delete(self, i):
        if 0 <= i < len(self.items):
            self.items.pop(i)
        return self.save()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "sequences": self.items}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return ""
        except OSError as e:
            return str(e)
