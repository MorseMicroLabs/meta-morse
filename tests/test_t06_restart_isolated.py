"""t06 / t07: restarting one supplicant leaves the other radio and its supplicant interfaces alone.

[s1g]       restart wpa_supplicant_s1g, watch the standard radio   (was t06)
[standard]  restart wpa_supplicant, watch the HaLow radio          (was t07)
"""
import time

import pytest

from dsup import journal, monitors, nm, supplicant

pytestmark = [pytest.mark.halow, pytest.mark.standard]


@pytest.mark.parametrize("restarted_name", ["s1g", "standard"])
def test_t06_restart_isolated(restarted_name, board, halow, standard, health, checks, evidence, settings):
    restarted, watched = (halow, standard) if restarted_name == "s1g" else (standard, halow)
    before = sorted(supplicant.interfaces(board, watched.svc, watched.path))
    since = board.now()
    with monitors.StateMonitor(board, "watched", watched.dev) as state, \
            monitors.PingMonitor(board, "watched", watched.dev, watched.gateway) as ping:
        board.run(f"systemctl restart {restarted.unit}")
        time.sleep(5)
        checks.ok(f"{restarted.name} radio reconnects",
                  nm.wait_connected(board, restarted.dev, settings.int("connect_timeout"))[0])
        time.sleep(5)
    evidence.save("statemon.txt", state.text)
    evidence.save("pingmon.txt", ping.text)
    log = journal.nm_journal(board, since)
    evidence.save("nm.log", log)
    after = sorted(supplicant.interfaces(board, watched.svc, watched.path))

    checks.eq(f"{watched.name} radio never left 'connected'", 0, state.not_connected)
    if state.unreachable:
        checks.info(f"NetworkManager was too busy to answer in {state.unreachable} of {state.samples} samples "
                    f"(the radio itself stayed up)")
    checks.le(f"{watched.name} radio never lost 3 probes in a row", 2, ping.longest_lost_run)
    if ping.lost:
        checks.info(f"{watched.name} radio lost {ping.lost} probes in all, longest run {ping.longest_lost_run}")
    checks.eq(f"the {watched.unit} supplicant still has the same interfaces", before, after)
    checks.lacks(f"NM did not remove {watched.name} interfaces because {restarted.unit} restarted", log,
                 rf'remove interface "{watched.path}/Interfaces/[0-9]+"')
    health.check(checks, evidence)
