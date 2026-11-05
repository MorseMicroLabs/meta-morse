"""t03: five release/create cycles leave no stale interface and no failed D-Bus calls."""
import time

import pytest

from dsup import bus, journal, nm, supplicant

pytestmark = [pytest.mark.halow]


def test_t03_managed_cycles(board, halow, health, checks, evidence):
    since = board.now()
    with bus.BusCapture(board) as cap:
        for i in range(1, 6):
            nm.set_managed(board, halow.dev, False)
            time.sleep(3)
            checks.eq(f"cycle {i}: interface gone after release", 0, supplicant.s1g_iface_count(board))
            nm.set_managed(board, halow.dev, True)
            if not nm.wait_connected(board, halow.dev, 60)[0]:
                break
        checks.eq("connected after the last cycle", "connected", nm.state(board, halow.dev))
        checks.eq("one interface at the end", 1, supplicant.s1g_iface_count(board))
        time.sleep(2)
    evidence.save("bus.txt", cap.text)
    evidence.save("nm.log", journal.nm_journal(board, since))
    checks.count_eq("one RemoveInterface per cycle, sent to the s1g service", 5, cap.text, bus.s1g_call("RemoveInterface"))
    checks.count_eq("one CreateInterface per cycle", 5, cap.text, bus.s1g_call("CreateInterface"))
    checks.lacks("no UnknownMethod / InterfaceExists on the bus", cap.text,
                 r"ErrorName=(org\.freedesktop\.DBus\.Error\.UnknownMethod|fi\.w1\.wpa_supplicant1_s1g\.InterfaceExists)")
    health.check(checks, evidence)
