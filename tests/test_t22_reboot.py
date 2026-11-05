import re
import shlex
import time

import pytest

from dsup import journal, nm, supplicant
from dsup.nm import first_attempt_checks

pytestmark = [pytest.mark.halow, pytest.mark.standard, pytest.mark.disruptive,
              pytest.mark.timeout(1500)]

CONF = "/etc/NetworkManager/conf.d/99-t22-trace.conf"


def test_t22_reboot(board, halow, standard, health, checks, evidence, settings):
    try:
        boot_before = board.sh("cat /proc/sys/kernel/random/boot_id")
        board.run(f"printf '[logging]\\nlevel=TRACE\\ndomains=SUPPLICANT,DEVICE,WIFI\\n' > {CONF}; sync")
        checks.info("rebooting; waiting for ssh (slow links: up to 300 s)")
        board.run("(sleep 2; reboot) >/dev/null 2>&1 &")
        time.sleep(20)
        up, waited = board.wait_ssh(300)
        checks.ok("board answers ssh again after the reboot", up)
        if not up:
            return
        checks.info(f"  ssh back after about {20 + waited:.0f} s")
        checks.ok("the board really rebooted (boot id changed)",
                  boot_before != board.sh("cat /proc/sys/kernel/random/boot_id"))
        # the reboot reset the core file setting of the run-wide guard: set it again
        core = settings.core_dir
        board.run(f"mkdir -p {shlex.quote(core)}; echo {shlex.quote(core + '/core.%e.%p')} > /proc/sys/kernel/core_pattern")
        health.snapshot()
        checks.ok("wlan0 connected", nm.wait_connected(board, halow.dev, 180)[0])
        checks.ok("wlan1 connected", nm.wait_connected(board, standard.dev, 180)[0])
        time.sleep(15)
        log = board.sh(f"journalctl -b --no-pager 2>/dev/null | grep -E {shlex.quote(journal.NM_FILTER)}", timeout=180)
        evidence.save("boot.log", log)

        checks.eq("NetworkManager was not restarted by systemd since boot", 0, nm.restarts(board))
        checks.lacks("no crash of NetworkManager since boot", log, journal.SEGV_PATTERN)
        checks.lacks("no GLib assertion from NetworkManager since boot", log, journal.GLIB_PATTERN)
        first_attempt_checks(checks, log, halow.dev)
        creates = len(re.findall(rf'supplicant: create-iface.*creating interface \(ifname "{halow.dev}"\)', log))
        checks.eq("exactly one create-iface attempt for wlan0 (no 10 s retry)", 1, creates)
        checks.info(f"  create-iface lines: {len(re.findall('supplicant: create-iface.*new request', log))} requests")
        checks.eq("one interface in wpa_supplicant_s1g", 1, supplicant.s1g_iface_count(board))
    finally:
        board.run(f"rm -f {CONF}")
