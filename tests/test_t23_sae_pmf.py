import re
import shlex
import time

import pytest

from dsup import journal, nm, supplicant

pytestmark = [pytest.mark.halow, pytest.mark.standard]


def _security_checks(board, checks, evidence, label, radio):
    km, pmf = radio.key_mgmt, radio.pmf
    conn = shlex.quote(radio.conn)
    checks.eq(f"{label}: profile '{radio.conn}' key-mgmt", km,
              board.sh(f"nmcli -g 802-11-wireless-security.key-mgmt connection show {conn}"))
    got = board.sh(f"nmcli -g 802-11-wireless-security.pmf connection show {conn}").split(" ")[0]
    checks.eq(f"{label}: profile '{radio.conn}' PMF is {pmf} (nmcli: 3 = required)", pmf, got)
    checks.eq(f"{label}: {radio.dev} is connected", "connected", nm.state(board, radio.dev))
    iface = supplicant.interface_for(board, radio.svc, radio.path, radio.dev)
    bss = None
    if iface:
        out = board.sh(f"busctl get-property {radio.svc} {iface} {radio.svc}.Interface CurrentBSS")
        bss = (re.findall(r'"([^"]*)"', out) or [None])[0]
    checks.ok(f"{label}: the supplicant reports a current BSS", bool(bss) and bss != "/")
    if not bss or bss == "/":
        return
    rsn = board.sh(f"busctl get-property {radio.svc} {bss} {radio.svc}.BSS RSN 2>/dev/null")
    evidence.save(f"rsn_{label.split()[0]}.txt", rsn)
    checks.count_eq(f"{label}: the BSS advertises {km} key management", 1, rsn, rf'"KeyMgmt" as [0-9]+ .*"{re.escape(km)}"')
    if pmf == "3":
        checks.has(f"{label}: the BSS advertises management frame protection (MgmtGroup)", rsn, '"MgmtGroup"')


def test_t23_sae_pmf(board, halow, standard, health, checks, evidence, settings):
    try:
        _security_checks(board, checks, evidence, "HaLow", halow)
        _security_checks(board, checks, evidence, "Standard", standard)

        caps = lambda: board.sh(f"busctl get-property {standard.svc} {standard.path} {standard.svc} Capabilities")
        before = caps()
        checks.info(f"stock supplicant capabilities before: {before}")
        since = board.now()
        board.run("systemctl restart wpa_supplicant_s1g")
        checks.ok("HaLow radio reconnects", nm.wait_connected(board, halow.dev, settings.int("connect_timeout"))[0])

        nm.set_managed(board, standard.dev, False)
        time.sleep(3)
        nm.set_managed(board, standard.dev, True)
        checks.ok("wlan1 reconnects after the s1g restart",
                  nm.wait_connected(board, standard.dev, settings.int("connect_timeout"))[0])
        after = caps()
        checks.info(f"stock supplicant capabilities after:  {after}")
        checks.eq("stock supplicant capabilities unchanged by the s1g restart", before, after)
        _security_checks(board, checks, evidence, "Standard (after s1g restart)", standard)
        log = journal.nm_journal(board, since)
        evidence.save("nm.log", log)
        checks.lacks("no \"Couldn't initialize supplicant interface\" for wlan1", log,
                     rf"device \({standard.dev}\).*Couldn't initialize supplicant interface")
    finally:
        nm.set_managed(board, standard.dev, True)
