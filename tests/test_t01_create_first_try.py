"""t01: after a clean release NetworkManager creates the HaLow interface with a single CreateInterface."""
import time

import pytest

from dsup import bus, journal, nm, supplicant

pytestmark = [pytest.mark.halow]


def test_t01_create_first_try(board, halow, health, checks, evidence):
    since = board.now()
    with bus.BusCapture(board) as cap:
        # Release the interface, then make sure wpa_supplicant_s1g has really forgotten it, so that
        # the next CreateInterface succeeds. Done with the s1g names, independently of NetworkManager.
        nm.set_managed(board, halow.dev, False)
        time.sleep(3)
        supplicant.s1g_remove_all_interfaces(board)
        checks.eq("wpa_supplicant_s1g has no interface left", 0, supplicant.s1g_iface_count(board))

        nm.set_managed(board, halow.dev, True)
        connected, _ = nm.wait_connected(board, halow.dev, 60)
        time.sleep(3)
    evidence.save("bus.txt", cap.text)
    log = evidence.save("nm.log", journal.nm_journal(board, since)).read_text()

    checks.ok("HaLow radio connected", connected)
    checks.lacks("NM did not drop the new interface as 'name owner changed'", log, "name owner changed")
    checks.lacks("NM did not fail to initialize the supplicant interface", log,
                 "Couldn't initialize supplicant interface")
    checks.count_eq("one CreateInterface sent to wpa_supplicant_s1g", 1, cap.text, bus.s1g_call("CreateInterface"))
    checks.lacks("no UnknownMethod error on the bus", cap.text, "ErrorName=org.freedesktop.DBus.Error.UnknownMethod")
    checks.eq("wpa_supplicant_s1g holds exactly one interface", 1, supplicant.s1g_iface_count(board))
    health.check(checks, evidence)
