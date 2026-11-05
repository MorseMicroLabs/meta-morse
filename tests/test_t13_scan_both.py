import time

import pytest

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t13_scan_both(board, halow, standard, health, checks, evidence):
    for r in (halow, standard):
        board.run(f"nmcli device wifi rescan ifname {r.dev}")
    time.sleep(8)
    for r in (halow, standard):
        n = board.sh(f"nmcli -t -f SSID device wifi list ifname {r.dev} 2>/dev/null | grep -c .")
        checks.ge(f"NM lists access points on {r.dev}", 1, n)
    checks.ge("wpa_supplicant_s1g exports BSS objects", 1,
              board.sh(f"busctl tree {halow.svc} | grep -c '/BSSs/[0-9]'"))
    checks.ge("the stock supplicant exports BSS objects", 1,
              board.sh(f"busctl tree {standard.svc} | grep -c '/BSSs/[0-9]'"))
    health.check(checks, evidence)
