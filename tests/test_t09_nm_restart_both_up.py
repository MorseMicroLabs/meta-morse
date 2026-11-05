"""t09: a plain NetworkManager restart brings both radios back."""
import pytest

from dsup import nm

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def test_t09_nm_restart_both_up(board, halow, standard, health, checks, evidence):
    board.run("systemctl restart NetworkManager")
    health.snapshot()                   # the restart is on purpose: compare with the new process
    nm.set_trace_logging(board)
    checks.ok("standard radio connects", nm.wait_connected(board, standard.dev, 60)[0])
    checks.ok("HaLow radio connects", nm.wait_connected(board, halow.dev, 60)[0])
    health.check(checks, evidence)
