import time

import pytest

from dsup import bus, journal, nm
from dsup.supplicant import S1G_SVC

pytestmark = [pytest.mark.halow]


def test_s06_nm_reactivates_s1g(board, halow, health, checks, evidence, settings):
    try:
        nmu = board.sh("busctl status org.freedesktop.NetworkManager 2>/dev/null | sed -n 's/^UniqueName=//p'")
        checks.info(f"  NetworkManager bus name: {nmu}")
        checks.ok("found NetworkManager's unique bus name", bool(nmu))

        with bus.BusCapture(board) as cap:
            since = board.now()
            board.run("systemctl stop wpa_supplicant_s1g")
            ok, waited = board.wait_for("systemctl is-active wpa_supplicant_s1g", 90, "s1g active again")
            checks.ok("s1g is started again without anybody calling it from the test", ok)
            checks.info(f"  s1g active again {waited:.0f}s after the stop (polled every 2 s)")
            time.sleep(5)
        evidence.save("bus.txt", cap.text)
        log = journal.nm_journal(board, since)
        evidence.save("nm.log", log)

        starts = bus.start_service_calls(cap.text, S1G_SVC)
        removed = bus.first_signal_epoch(cap.text, S1G_SVC, "InterfaceRemoved")
        checks.info(f"  StartServiceByName calls: {starts}; InterfaceRemoved at {removed}")
        checks.ok("StartServiceByName for the s1g name was sent", len(starts) >= 1)
        checks.ok(f"...by NetworkManager ({nmu})", bool(starts) and all(sender == nmu for _, sender in starts))
        checks.eq("no other sender started the s1g name", 1, len(starts))
        checks.has("NM logged the poke", log, r'poke service "fi.w1.wpa_supplicant1_s1g"|name owner ":[0-9.]+" appeared')
        if removed and starts and starts[0][0]:
            delay = starts[0][0] - removed
            checks.info(f"  s1g InterfaceRemoved -> NM StartServiceByName: {delay:.1f}s")
            checks.le("NM re-activates within the 60 s availability reset", 60, delay)
        checks.ok("HaLow radio connects again",
                  nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])
    finally:
        board.run("systemctl start wpa_supplicant_s1g")
