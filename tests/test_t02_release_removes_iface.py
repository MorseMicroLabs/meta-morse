"""t02: releasing the HaLow radio removes its interface from wpa_supplicant_s1g without an UnknownMethod error.

Two capture windows: the release (managed no, where RemoveInterface is sent) and the re-create
(managed yes). The UnknownMethod check applies to the release window.
"""
import time

import pytest

from dsup import bus, journal, nm, supplicant

pytestmark = [pytest.mark.halow]


def test_t02_release_removes_iface(board, halow, health, checks, evidence):
    since = board.now()

    with bus.BusCapture(board) as rel:
        nm.set_managed(board, halow.dev, False)
        time.sleep(5)
    evidence.save("bus_release.txt", rel.text)
    checks.eq("wpa_supplicant_s1g removed the interface on release", 0, supplicant.s1g_iface_count(board))
    checks.count_eq("exactly one RemoveInterface was sent, to the s1g service with the s1g interface name",
                    1, rel.text, bus.s1g_call("RemoveInterface"))
    checks.count_eq("no RemoveInterface went to the stock service", 0, rel.text, bus.stock_call("RemoveInterface"))
    checks.lacks("no UnknownMethod during the release", rel.text, "ErrorName=org.freedesktop.DBus.Error.UnknownMethod")

    with bus.BusCapture(board) as cre:
        nm.set_managed(board, halow.dev, True)
        checks.ok("HaLow radio connected again", nm.wait_connected(board, halow.dev, 60)[0])
        time.sleep(2)
    evidence.save("bus_create.txt", cre.text)
    checks.eq("exactly one interface after the re-create", 1, supplicant.s1g_iface_count(board))
    checks.lacks("no InterfaceExists / UnknownMethod during the re-create", cre.text,
                 r"ErrorName=(fi\.w1\.wpa_supplicant1_s1g\.InterfaceExists|org\.freedesktop\.DBus\.Error\.UnknownMethod)")

    log = journal.nm_journal(board, since)
    evidence.save("nm.log", log)
    checks.lacks("no warning about the disconnect during release", log, "<warn>.*call-disconnect")
    health.check(checks, evidence)
