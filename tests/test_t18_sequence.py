import time

import pytest

from dsup import bus, journal, monitors, nm, supplicant

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t18_sequence(board, halow, standard, health, checks, evidence, settings):
    mon = monitors.SequenceMonitor(board, "t18", halow.dev)
    try:
        checks.info("step 1: fresh start of both supplicants (-u) with NetworkManager stopped")
        board.run("systemctl stop NetworkManager wpa_supplicant_s1g wpa_supplicant; sleep 2; "
                  "systemctl start wpa_supplicant wpa_supplicant_s1g; sleep 3")
        running = board.sh("ps | grep -E '[w]pa_supplicant(_s1g)? -u'")
        evidence.save("supplicants.txt", running)
        checks.info("  running: " + " ; ".join(ln.strip() for ln in running.splitlines()))
        checks.has("wpa_supplicant runs with -u", running, r"/usr/sbin/wpa_supplicant -u")
        checks.has("wpa_supplicant_s1g runs with -u", running, r"/usr/sbin/wpa_supplicant_s1g -u")
        checks.eq("wpa_supplicant_s1g starts without interfaces", 0, supplicant.s1g_iface_count(board))

        checks.info(f"step 2: start NetworkManager, it manages {halow.dev}")
        mon.start()
        with bus.BusCapture(board) as cap:
            board.run("systemctl start NetworkManager")
            health.snapshot()           # NetworkManager was started on purpose
            connected, waited = nm.wait_connected(board, halow.dev, 90)
            checks.info(f"  {halow.dev} connected={'yes' if connected else 'NO'} after {waited:.0f}s")
            time.sleep(15)              # long enough to see the ~10 s retry if there is one
            step2 = mon.fetch()
            evidence.save("mon_step2.txt", mon.text)
            checks.ok("HaLow radio connected", connected)
            evidence.save("nm_step2.log", journal.nm_journal(board, health.since))

            up0 = step2[0][0] if step2 else 0
            first_up = next((r[0] for r in step2 if r[2] >= 1), None)
            first_conn = next((r[0] for r in step2 if r[3] == "connected"), None)
            dropped = sum(1 for r in step2 if first_up is not None and r[0] > first_up and r[2] == 0)
            checks.info(f"  s1g interface appeared at +{(first_up or 0) - up0:.0f}s, {halow.dev} connected at "
                        f"+{(first_conn or 0) - up0:.0f}s, samples where it vanished again: {dropped}")
            checks.eq("s1g interface was never dropped after it appeared (no retry)", 0, dropped)

            checks.info("step 3: systemctl stop wpa_supplicant_s1g, watching NetworkManager for 40 s")
            t3 = board.uptime_s()
            board.run("systemctl stop wpa_supplicant_s1g")
            time.sleep(40)
            rows = mon.fetch()
            mon.stop()
        evidence.save("mon_all.txt", mon.text)
        evidence.save("bus.txt", cap.text)
        crash_at = next((r[0] - t3 for r in rows if r[0] > t3 and r[1] != health.pid), None)
        checks.info(f"  NetworkManager main pid changed {crash_at:.0f}s after the stop" if crash_at is not None
                    else "  NetworkManager main pid unchanged for 40 s after the stop")
        checks.ok("NetworkManager pid unchanged for 40 s after stopping s1g", crash_at is None)
        health.check(checks, evidence)
        checks.eq("standard radio is still connected", "connected", nm.state(board, standard.dev))

        board.run("systemctl start wpa_supplicant_s1g")
        checks.ok("HaLow radio returns once s1g is back",
                  nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])
        log = journal.nm_journal(board, health.since)
        evidence.save("nm.log", log)
        checks.lacks("NM never reported the create race", log, "name owner changed since creating")
    finally:
        mon.stop()
        board.run("systemctl start wpa_supplicant_s1g")
