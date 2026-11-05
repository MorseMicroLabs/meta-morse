import time

import pytest

from dsup import bus, journal, nm
from dsup.nm import first_attempt_checks
from dsup.supplicant import S1G_SVC

pytestmark = [pytest.mark.halow]


def test_t20a_nm_first_s1g_activated_by_nm(board, halow, health, checks, evidence, settings):
    try:
        checks.info("phase A: s1g stopped, NetworkManager starts and activates it")
        board.run("systemctl stop NetworkManager wpa_supplicant_s1g")
        checks.eq("A: s1g is not running before NetworkManager starts", "inactive",
                  nm.unit_state(board, "wpa_supplicant_s1g"))
        since = board.now()
        with bus.BusCapture(board) as cap:
            board.run("systemctl start NetworkManager")
            health.snapshot()
            ok, waited = nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))
            checks.ok("A: wlan0 connected", ok)
            checks.info(f"  A: wlan0 connected after {waited:.0f}s (polled every 2 s)")
            time.sleep(15)
        evidence.save("bus_a.txt", cap.text)
        log = journal.nm_journal(board, since)
        evidence.save("nm_a.log", log)
        first_attempt_checks(checks, log, halow.dev, cap.text)
        checks.eq("A: s1g was started", "active", nm.unit_state(board, "wpa_supplicant_s1g"))
    finally:
        board.run("systemctl unmask --runtime wpa_supplicant_s1g; systemctl start wpa_supplicant_s1g NetworkManager")


def test_t20b_nm_first_s1g_appears_late(board, halow, standard, health, checks, evidence, settings):
    limit = settings.float("recovery_limit")
    try:
        checks.info("phase B: s1g absent (masked) for 10 s, then it appears")
        board.run("systemctl stop NetworkManager wpa_supplicant_s1g; systemctl mask --runtime wpa_supplicant_s1g")
        checks.eq("B: precondition: s1g unit is masked", "masked-runtime",
                  board.sh("systemctl is-enabled wpa_supplicant_s1g 2>/dev/null"))
        board.run("systemctl start NetworkManager")
        health.snapshot()
        time.sleep(10)
        checks.eq("B: NetworkManager is running without s1g", "active", nm.unit_state(board, "NetworkManager"))
        checks.eq("B: s1g is not running", "inactive", nm.unit_state(board, "wpa_supplicant_s1g"))
        checks.info(f"  B: wlan0 state with s1g absent: {nm.state(board, halow.dev)}")
        # wlan1 needs a scan, the handshake and DHCP, which can take longer than the 10 s above
        up, waited = nm.wait_connected(board, standard.dev, settings.int("connect_timeout"))
        checks.ok("B: standard radio connects although s1g is absent", up)
        checks.info(f"  B: wlan1 connected {10 + waited:.0f}s after NetworkManager started (s1g still absent)")

        with bus.BusCapture(board) as cap:
            time.sleep(2)
            # the window for the first-attempt criteria starts on the board, in the same command that
            # unmasks s1g (an error NetworkManager logged while s1g was masked does not count)
            since = board.run("date '+%Y-%m-%d %H:%M:%S'; systemctl unmask --runtime wpa_supplicant_s1g "
                              ">/dev/null 2>&1; systemctl start wpa_supplicant_s1g >/dev/null 2>&1"
                              ).out.splitlines()[0]
            checks.ok("B: s1g owns its D-Bus name",
                      board.wait_for(f"busctl --no-pager list | grep -qE '^{S1G_SVC} +[0-9]+ '", 60, "s1g owner")[0])
            activated = journal.wait_activated_after(board, halow.dev, since, 0, 120)
            checks.ok("B: wlan0 reached 'activated'", activated is not None)
            time.sleep(3)
        evidence.save("bus_b.txt", cap.text)
        owner = bus.owner_appeared(cap.text, S1G_SVC)
        if owner is not None and activated is not None:
            delay = activated - owner
            checks.info(f"  B: wlan0 activated {delay:.1f}s after s1g owned its name")
            checks.le(f"B: wlan0 connected within {limit:g}s of s1g owning its name", limit, delay)
        everything = journal.nm_journal(board, since)
        evidence.save("nm_b_all.log", everything)
        # NetworkManager's poke started while the unit was masked fails a moment after the unmask
        # ("Failed to D-Bus activate"). It is not about the bring-up that follows: apply the criteria
        # from the moment s1g owns its D-Bus name.
        log = journal.log_after_epoch(everything, owner or 0)
        evidence.save("nm_b.log", log)
        marker = "Couldn't initialize"
        checks.info(f"  B: {everything.count(marker)} \"{marker}\" line(s) while s1g was masked/starting, "
                    f"{log.count(marker)} after it owned its name")
        first_attempt_checks(checks, log, halow.dev, cap.text)
    finally:
        board.run("systemctl unmask --runtime wpa_supplicant_s1g; systemctl start wpa_supplicant_s1g NetworkManager")
