import time

import pytest

from dsup import bus, supplicant
from dsup.supplicant import S1G_PATH, S1G_SVC, STOCK_SVC

pytestmark = [pytest.mark.halow]


def test_s04_error_name_contract(board, halow, health, checks, evidence):
    with bus.BusCapture(board) as cap:
        board.run(f"busctl call {S1G_SVC} {S1G_PATH} {S1G_SVC} CreateInterface 'a{{sv}}' 2 Ifname s {halow.dev} Driver s nl80211")
        board.run(f"busctl call {S1G_SVC} {S1G_PATH} {S1G_SVC} GetInterface s nosuch0")
        board.run(f"busctl call {S1G_SVC} {S1G_PATH} {STOCK_SVC} GetInterface s {halow.dev}")
        time.sleep(1)
    evidence.save("bus.txt", cap.text)
    checks.has(f"CreateInterface on an existing interface -> {S1G_SVC}.InterfaceExists", cap.text,
               f"ErrorName={S1G_SVC}.InterfaceExists")
    checks.has(f"GetInterface of an unknown interface -> {S1G_SVC}.InterfaceUnknown", cap.text,
               f"ErrorName={S1G_SVC}.InterfaceUnknown")
    checks.has("the stock interface name is not served by the s1g service", cap.text,
               r"ErrorName=org\.freedesktop\.DBus\.Error\.(UnknownInterface|UnknownMethod|UnknownObject)")
    checks.eq("the existing interface was not duplicated", 1, supplicant.s1g_iface_count(board))
