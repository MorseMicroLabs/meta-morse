import time

import pytest

from dsup import bus, journal, nm, supplicant
from dsup.nm import first_attempt_checks

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t21_order_s1g_first(board, halow, standard, health, checks, evidence, settings):
    timeout = settings.int("connect_timeout")
    checks.info("stop NetworkManager, restart both supplicants, let them settle, then start NetworkManager")
    board.run("systemctl stop NetworkManager; systemctl restart wpa_supplicant wpa_supplicant_s1g; sleep 5")
    checks.eq("s1g is running before NetworkManager", "active", nm.unit_state(board, "wpa_supplicant_s1g"))
    checks.eq("s1g has no interface yet", 0, supplicant.s1g_iface_count(board))
    since = board.now()
    with bus.BusCapture(board) as cap:
        board.run("systemctl start NetworkManager")
        health.snapshot()
        ok, waited = nm.wait_connected(board, halow.dev, timeout)
        checks.ok("wlan0 connected", ok)
        checks.info(f"  wlan0 connected after {waited:.0f}s (polled every 2 s)")
        checks.ok("wlan1 connected", nm.wait_connected(board, standard.dev, timeout)[0])
        time.sleep(15)                  # a retry, if there is one, would show up here
    evidence.save("bus.txt", cap.text)
    log = journal.nm_journal(board, since)
    evidence.save("nm.log", log)
    first_attempt_checks(checks, log, halow.dev, cap.text)
    checks.eq("one interface in wpa_supplicant_s1g", 1, supplicant.s1g_iface_count(board))
    health.check(checks, evidence)
