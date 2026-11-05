import shlex
import time

import pytest

from dsup import nm, supplicant

RADIOS = [pytest.param("halow", marks=pytest.mark.halow), pytest.param("standard", marks=pytest.mark.standard)]

@pytest.mark.parametrize("radio", RADIOS, indirect=True)
def test_t10_connect_cycle(radio, board, health, checks, evidence):
    conn = shlex.quote(radio.conn)
    for i in (1, 2, 3):
        board.run(f"nmcli connection down {conn}")
        time.sleep(3)
        board.run(f"nmcli connection up {conn} ifname {radio.dev}", timeout=120)
        checks.ok(f"cycle {i}: connected", nm.wait_connected(board, radio.dev, 60)[0])
        time.sleep(2)
        answers = board.sh(f"ping -I {radio.dev} -c3 -W2 {radio.gateway} 2>/dev/null | grep -c 'bytes from'")
        checks.ge(f"cycle {i}: gateway answers over {radio.dev}", 2, answers)
        if radio.name == "halow":
            checks.eq(f"cycle {i}: one s1g interface", 1, supplicant.s1g_iface_count(board))
    health.check(checks, evidence)
