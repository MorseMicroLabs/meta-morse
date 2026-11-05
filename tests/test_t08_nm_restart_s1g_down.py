"""t08: NetworkManager restarted while wpa_supplicant_s1g is down: the standard radio must come up, the HaLow radio follows s1g."""
import time

import pytest

from dsup import journal, nm, supplicant

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t08_nm_restart_s1g_down(board, halow, standard, health, checks, evidence, settings):
    try:
        board.run("systemctl stop wpa_supplicant_s1g")
        time.sleep(8)
        if nm.unit_state(board, "NetworkManager") != "active":
            board.run("systemctl start NetworkManager")
        time.sleep(3)

        since = board.now()
        board.run("systemctl restart NetworkManager")
        health.snapshot()               # the restart is on purpose: compare with the new process
        nm.set_trace_logging(board)

        checks.ok("standard radio comes up although wpa_supplicant_s1g is down",
                  nm.wait_connected(board, standard.dev, 60)[0])
        time.sleep(10)
        health.check(checks, evidence)
        evidence.save("nm.log", journal.nm_journal(board, since))
        # NetworkManager restarts at log level INFO, so TRACE-only lines cannot be asserted here;
        # look at the supplicant instead: the standard radio must have an interface there.
        checks.ok(f"the stock supplicant holds an interface for {standard.dev}",
                  supplicant.interface_for(board, standard.svc, standard.path, standard.dev) is not None)

        board.run("systemctl start wpa_supplicant_s1g")
        checks.ok("HaLow radio connects once wpa_supplicant_s1g is back, without a manual toggle",
                  nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])
    finally:
        board.run("systemctl start wpa_supplicant_s1g")
