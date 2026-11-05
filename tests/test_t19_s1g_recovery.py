import time

import pytest

from dsup import bus, journal, nm, supplicant
from dsup.supplicant import S1G_SVC

pytestmark = [pytest.mark.halow]

DROPIN = "/run/systemd/system/wpa_supplicant_s1g.service.d"
MAINPID = "$(systemctl show -p MainPID --value wpa_supplicant_s1g)"
CASES = {
    "restart": "systemctl restart wpa_supplicant_s1g",
    "kill-9": f"kill -9 {MAINPID}",
    "kill-term": f"kill -TERM {MAINPID}",
}


@pytest.fixture
def restart_always(board, checks):
    board.run(f"mkdir -p {DROPIN} && printf '[Service]\\nRestart=always\\nRestartSec=1\\n' > {DROPIN}/t19.conf "
              "&& systemctl daemon-reload")
    checks.eq("test setup: wpa_supplicant_s1g has Restart=always", "always",
              board.sh("systemctl show -p Restart --value wpa_supplicant_s1g"))
    yield
    board.run(f"rm -rf {DROPIN}; systemctl daemon-reload; systemctl start wpa_supplicant_s1g")


@pytest.mark.parametrize("case", list(CASES))
def test_t19_s1g_recovery(case, restart_always, board, halow, standard, health, checks, evidence, settings):
    limit = settings.float("recovery_limit")
    checks.info(f"case '{case}': {CASES[case]}")
    oldpid = board.sh("systemctl show -p MainPID --value wpa_supplicant_s1g")
    since = board.now()
    with bus.BusCapture(board) as cap:
        board.run(CASES[case])
        ok, _ = board.wait_for(
            f"p=$(systemctl show -p MainPID --value wpa_supplicant_s1g); [ \"$p\" != 0 ] && [ \"$p\" != {oldpid} ] "
            f"&& busctl --no-pager list | grep -qE '^{S1G_SVC} +[0-9]+ '",
            60, "new s1g process with owner")
        checks.ok(f"{case}: a new wpa_supplicant_s1g process owns its D-Bus name again", ok)
        time.sleep(1)
    evidence.save(f"bus_{case}.txt", cap.text)
    owner = bus.owner_appeared(cap.text, S1G_SVC)
    checks.ok(f"{case}: the bus capture shows the s1g name getting a new owner", owner is not None)
    if owner is not None:
        activated = journal.wait_activated_after(board, halow.dev, since, owner, 90)
        if activated is None:
            checks.ok(f"{case}: wlan0 reached 'activated' after s1g came back (90 s)", False)
        else:
            delay = activated - owner
            checks.info(f"  {case}: wlan0 activated {delay:.1f}s after s1g owned its name again (limit {limit:g}s)")
            evidence.save("delay.txt", f"{case} {delay:.1f}s\n")
            checks.le(f"{case}: wlan0 connected within {limit:g}s of the name owner returning", limit, delay)
            if delay < 0:
                checks.info("  (negative delay: wlan0 was activated before the name returned; "
                            "NetworkManager did not notice the outage)")
    checks.eq(f"{case}: one interface in wpa_supplicant_s1g", 1, supplicant.s1g_iface_count(board))
    checks.eq(f"{case}: standard radio still connected", "connected", nm.state(board, standard.dev))
