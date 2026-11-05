"""t04: stopping wpa_supplicant_s1g must not crash NetworkManager or touch the standard radio."""
import time

import pytest

from dsup import journal, monitors, nm

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t04_s1g_stop_nm_survives(board, halow, standard, health, checks, evidence, settings):
    since = board.now()
    try:
        with monitors.StateMonitor(board, "std", standard.dev) as state, \
                monitors.PingMonitor(board, "std", standard.dev, standard.gateway) as ping:
            board.run("systemctl stop wpa_supplicant_s1g")
            time.sleep(20)

            # health first: if NetworkManager crashed, the rest is academic but still reported
            health.check(checks, evidence)
            checks.eq("standard radio is still connected", "connected", nm.state(board, standard.dev))
            state.stop()
            ping.stop()
        evidence.save("statemon.txt", state.text)
        evidence.save("pingmon.txt", ping.text)
        checks.eq("standard radio never left 'connected' while s1g was stopped", 0, state.not_connected)
        if state.unreachable:
            checks.info(f"NetworkManager was too busy to answer in {state.unreachable} of {state.samples} samples "
                        f"(the radio itself stayed up)")
        checks.le("standard radio never lost 3 probes in a row", 2, ping.longest_lost_run)
        if ping.lost:
            checks.info(f"standard radio lost {ping.lost} single probes, longest run {ping.longest_lost_run}")

        log = journal.nm_journal(board, since)
        evidence.save("nm.log", log)
        checks.lacks("NM did not tear down the stock supplicant interface", log,
                     r'remove interface "/fi/w1/wpa_supplicant1/Interfaces/[0-9]+".*name-owner changed')

        # and bring it back: the HaLow radio must recover without help
        board.run("systemctl start wpa_supplicant_s1g")
        checks.ok("HaLow radio reconnects by itself after wpa_supplicant_s1g is back",
                  nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])
    finally:
        board.run("systemctl start wpa_supplicant_s1g")
