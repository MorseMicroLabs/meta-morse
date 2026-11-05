import shlex
import time

import pytest

from dsup import nm

pytestmark = [pytest.mark.halow]

RACE_SH = """#!/bin/sh
i=0
while [ $i -lt 20 ]; do
    nmcli connection up {conn} ifname {dev} >/dev/null 2>&1 &
    sleep 0.$((i % 7 + 1))
    nmcli device disconnect {dev} >/dev/null 2>&1
    wait
    i=$((i + 1))
done
"""


def test_t15_assoc_cancel_race(board, halow, health, checks, evidence, settings):
    conn = shlex.quote(halow.conn)
    try:
        board.put_text(RACE_SH.format(conn=conn, dev=halow.dev), "/tmp/dsup_assoc_race.sh")
        board.run("/tmp/dsup_assoc_race.sh", timeout=600)
        time.sleep(5)
        health.check(checks, evidence)
        board.run(f"nmcli connection up {conn} ifname {halow.dev}", timeout=120)
        checks.ok("HaLow radio connects again after the storm", nm.wait_connected(board, halow.dev, 60)[0])
        checks.le("wpa_supplicant_s1g holds at most one network entry", 1,
                  board.sh(f"busctl tree {halow.svc} | grep -c '/Networks/[0-9]'"))
    finally:
        board.run(f"nmcli connection up {conn} ifname {halow.dev}", timeout=120)
        board.run("rm -f /tmp/dsup_assoc_race.sh")
