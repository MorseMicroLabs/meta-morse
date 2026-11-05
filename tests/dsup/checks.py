import re
import time


def _first_lines(text, pattern, n=3):
    hits = [ln for ln in text.splitlines() if re.search(pattern, ln)]
    return " | ".join(h.strip()[:220] for h in hits[:n])


class Checks:
    def __init__(self, redact=lambda t: t):
        self.lines = []
        self.failures = []
        self.count = 0
        self._redact = redact

    def info(self, msg):
        self.lines.append(self._redact(f"[{time.strftime('%H:%M:%S')}] {msg}"))

    def _result(self, ok, msg):
        self.count += 1
        msg = self._redact(msg)
        if ok:
            self.lines.append(f"    PASS: {msg}")
        else:
            self.failures.append(msg)
            self.lines.append(f"    FAIL: {msg}")
        return ok

    def ok(self, desc, condition):
        return self._result(bool(condition), desc)

    def eq(self, desc, expected, actual):
        if str(expected) == str(actual):
            return self._result(True, f"{desc} (= {actual})")
        return self._result(False, f"{desc}: expected '{expected}', got '{actual}'")

    def le(self, desc, limit, actual):
        try:
            good = float(actual) <= float(limit)
        except (TypeError, ValueError):
            good = False
        return self._result(good, f"{desc} ({actual} <= {limit})" if good else f"{desc}: expected <= {limit}, got '{actual}'")

    def ge(self, desc, limit, actual):
        try:
            good = float(actual) >= float(limit)
        except (TypeError, ValueError):
            good = False
        return self._result(good, f"{desc} ({actual} >= {limit})" if good else f"{desc}: expected >= {limit}, got '{actual}'")

    def has(self, desc, text, pattern):
        if re.search(pattern, text, re.M):
            return self._result(True, desc)
        return self._result(False, f"{desc}: pattern not found: {pattern}")

    def lacks(self, desc, text, pattern):
        if re.search(pattern, text, re.M):
            return self._result(False, f"{desc}: unexpected: {_first_lines(text, pattern)}")
        return self._result(True, desc)

    def count_eq(self, desc, expected, text, pattern):
        n = sum(1 for ln in text.splitlines() if re.search(pattern, ln))
        return self.eq(desc, expected, n)

    def render(self):
        head = f"checks: {self.count}, failed: {len(self.failures)}"
        return "\n".join(self.lines + [head])

    def failure_text(self):
        return f"{len(self.failures)} of {self.count} checks failed:\n" + "\n".join(f"  - {f}" for f in self.failures)
