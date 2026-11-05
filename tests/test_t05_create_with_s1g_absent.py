import time

import pytest

from dsup import journal, nm

pytestmark = [pytest.mark.halow]


def test_t05_create_with_s1g_absent(board, halow, standard, health, checks, evidence, settings):
    since = board.now()
    try:
        board.run("systemctl stop wpa_supplicant_s1g")
        time.sleep(6)
        if nm.unit_state(board, "NetworkManager") != "active":
            board.run("systemctl start NetworkManager")
        time.sleep(3)
        health.snapshot()

        nm.set_managed(board, halow.dev, False)
        time.sleep(2)
        nm.set_managed(board, halow.dev, True)
        time.sleep(15)

        health.check(checks, evidence)
        checks.eq("standard radio is still connected", "connected", nm.state(board, standard.dev))

        active = nm.unit_state(board, "wpa_supplicant_s1g")
        checks.info(f"  wpa_supplicant_s1g after the create request: {active} (active = D-Bus activated by NetworkManager)")
        if active != "active":
            board.run("systemctl start wpa_supplicant_s1g")

        checks.ok("HaLow radio connects without another manual toggle",
                  nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])
        evidence.save("nm.log", journal.nm_journal(board, since))
    finally:
        board.run("systemctl start wpa_supplicant_s1g")
        nm.set_managed(board, halow.dev, True)
