import time

import pytest

from dsup import bus, nm, supplicant
from dsup.supplicant import S1G_PATH, S1G_SVC, STOCK_PATH, STOCK_SVC

pytestmark = [pytest.mark.halow]


def test_s05_interface_signals(board, halow, health, checks, evidence):
    try:
        nm.set_managed(board, halow.dev, False)
        time.sleep(4)
        supplicant.s1g_remove_all_interfaces(board)
        checks.eq("no interface left in wpa_supplicant_s1g", 0, supplicant.s1g_iface_count(board))

        with bus.BusCapture(board) as cap:
            board.run(f"busctl call {S1G_SVC} {S1G_PATH} {S1G_SVC} CreateInterface 'a{{sv}}' 2 Ifname s {halow.dev} Driver s nl80211")
            time.sleep(2)
            supplicant.s1g_remove_all_interfaces(board)
            time.sleep(2)
        evidence.save("bus.txt", cap.text)
        checks.has(f"InterfaceAdded is emitted as {S1G_SVC}.InterfaceAdded", cap.text,
                   rf"Path={S1G_PATH} +Interface={S1G_SVC} +Member=InterfaceAdded")
        checks.has(f"InterfaceRemoved is emitted as {S1G_SVC}.InterfaceRemoved", cap.text,
                   rf"Path={S1G_PATH} +Interface={S1G_SVC} +Member=InterfaceRemoved")
        checks.lacks("nothing is emitted under the stock path while only s1g was touched", cap.text,
                     rf"Path={STOCK_PATH} +Interface={STOCK_SVC} +Member=Interface(Added|Removed)")
    finally:
        nm.set_managed(board, halow.dev, True)
