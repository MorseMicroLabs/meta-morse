import time

import pytest

from dsup import monitors

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t12_concurrent_traffic(board, halow, standard, health, checks, evidence):
    with monitors.PingMonitor(board, "halow", halow.dev, halow.gateway) as h, \
            monitors.PingMonitor(board, "std", standard.dev, standard.gateway) as s:
        time.sleep(30)
    evidence.save("pingmon_halow.txt", h.text)
    evidence.save("pingmon_standard.txt", s.text)
    checks.ge("HaLow probes answered", 20, h.ok)
    checks.le("HaLow probes lost", 3, h.lost)
    checks.ge("standard probes answered", 20, s.ok)
    checks.le("standard probes lost", 3, s.lost)
    health.check(checks, evidence)
