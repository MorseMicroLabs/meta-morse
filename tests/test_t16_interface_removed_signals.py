import shlex
import time

import pytest

from dsup import journal, nm, supplicant

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def _removed_case(board, checks, evidence, settings, label, radio, iface_path):
    since = board.now()
    checks.info(f"  {label}: RemoveInterface {iface_path} behind NetworkManager's back")
    board.run(f"busctl call {radio.svc} {radio.path} {radio.svc} RemoveInterface o {shlex.quote(iface_path)}")
    time.sleep(3)
    log = journal.nm_journal(board, since)
    evidence.save(f"nm_{label}.log", log)
    checks.has(f"{label}: NM saw the InterfaceRemoved signal", log, "InterfaceRemoved signal from wpa_supplicant")
    checks.ok(f"{label}: {radio.dev} recovers", nm.wait_connected(board, radio.dev, settings.int("connect_timeout"))[0])


def test_t16_interface_removed_signals(board, halow, standard, health, restore, checks, evidence, settings):
    p = (supplicant.s1g_interfaces(board) or [None])[0]
    checks.ok("found the HaLow interface in wpa_supplicant_s1g", p is not None)
    if p:
        _removed_case(board, checks, evidence, settings, "halow", halow, p)

    restore()
    p = supplicant.interface_for(board, standard.svc, standard.path, standard.dev)
    checks.ok(f"found the {standard.dev} interface in the stock supplicant", p is not None)
    if p:
        _removed_case(board, checks, evidence, settings, "standard", standard, p)

    health.check(checks, evidence)
