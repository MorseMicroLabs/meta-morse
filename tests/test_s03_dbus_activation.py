import time

import pytest

from dsup import bus, journal, nm
from dsup.supplicant import S1G_PATH, S1G_SVC, bus_names

pytestmark = [pytest.mark.halow]


def test_s03_dbus_activation(board, halow, health, checks, evidence, settings):
    try:
        checks.info("NetworkManager stopped for the whole activation check")
        board.run("systemctl stop NetworkManager")
        board.run("systemctl stop wpa_supplicant_s1g")
        since = board.now()

        time.sleep(20)
        checks.eq("control: s1g stays inactive for 20 s with NetworkManager stopped", "inactive",
                  nm.unit_state(board, "wpa_supplicant_s1g"))
        checks.ok("control: the s1g bus name has no owner (it is only listed as activatable)",
                  S1G_SVC not in bus_names(board))

        with bus.BusCapture(board) as cap:
            board.run(f"busctl get-property {S1G_SVC} {S1G_PATH} {S1G_SVC} DebugLevel")
            checks.ok("wpa_supplicant_s1g.service was started by D-Bus activation",
                      board.wait_for("systemctl is-active wpa_supplicant_s1g", 15, "s1g active")[0])
        evidence.save("bus.txt", cap.text)
        checks.ok("the s1g name has an owner again", S1G_SVC in bus_names(board))
        checks.eq("NetworkManager was not running (so it did not call the s1g name)", 0,
                  board.sh("ps | grep -c '[/]usr/sbin/NetworkManager'"))
        log = journal.nm_journal(board, since)
        evidence.save("nm.log", log)
        checks.has("the supplicant started (journal)", log,
                   r"wpa_supplicant_s1g\[[0-9]+\]: Successfully initialized wpa_supplicant")

        board.run("systemctl start NetworkManager")
        health.snapshot()               # the restart was on purpose
        checks.ok("NetworkManager reconnects the HaLow radio",
                  nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])
    finally:
        board.run("systemctl start wpa_supplicant_s1g; systemctl start NetworkManager")
