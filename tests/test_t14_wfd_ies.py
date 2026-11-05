import time

import pytest

from dsup import journal, nm

pytestmark = [pytest.mark.standard]


def test_t14_wfd_ies(board, standard, health, checks, evidence):
    since = board.now()
    nm.set_managed(board, standard.dev, False)
    time.sleep(4)
    nm.set_managed(board, standard.dev, True)
    checks.ok("standard radio reconnects", nm.wait_connected(board, standard.dev, 60)[0])
    time.sleep(3)
    log = journal.nm_journal(board, since)
    evidence.save("nm.log", log)
    checks.has("NM set the WFD IEs", log, "setting WFD IEs for P2P operation")
    checks.lacks("no g_variant_builder assertion", log, "g_variant_builder")
    health.check(checks, evidence)
