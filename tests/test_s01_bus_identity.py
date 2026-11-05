import re

import pytest

from dsup.supplicant import (S1G_PATH, S1G_SVC, STOCK_PATH, STOCK_SVC, bus_names,
                             introspect_names, s1g_interfaces)

pytestmark = [pytest.mark.halow, pytest.mark.standard]

STOCK_NAMED = r"^fi\.w1\.wpa_supplicant1($|\.)"


def test_s01_bus_identity(board, checks, evidence):
    names = bus_names(board)
    evidence.save("busctl_list.txt", board.sh("busctl --no-pager list"))
    stock, s1g = names.get(STOCK_SVC), names.get(S1G_SVC)
    checks.ok("the stock supplicant owns fi.w1.wpa_supplicant1", stock is not None)
    checks.ok("wpa_supplicant_s1g owns fi.w1.wpa_supplicant1_s1g", s1g is not None)
    checks.ok("the two supplicants are different bus connections",
              stock is not None and s1g is not None and stock[1] != s1g[1])

    s1g_root = "\n".join(introspect_names(board, S1G_SVC, S1G_PATH))
    evidence.save("names_s1g_root.txt", s1g_root)
    checks.has("s1g root exports the s1g interface", s1g_root, f"^{re.escape(S1G_SVC)}$")
    checks.lacks("s1g root exports no stock-named interface", s1g_root, STOCK_NAMED)

    stock_root = "\n".join(introspect_names(board, STOCK_SVC, STOCK_PATH))
    evidence.save("names_stock_root.txt", stock_root)
    checks.has("stock root exports the stock interface", stock_root, f"^{re.escape(STOCK_SVC)}$")
    checks.lacks("stock root exports no s1g-named interface", stock_root, "_s1g")

    tree = board.sh(f"busctl tree {S1G_SVC}")
    iface = (s1g_interfaces(board) or [None])[0]
    objects = [iface]
    for kind in ("BSSs", "Networks"):
        m = re.search(re.escape(iface or "?") + rf"/{kind}/[0-9]+", tree)
        objects.append(m.group(0) if m else None)
    for obj in objects:
        if not obj:
            checks.ok("found an s1g object to introspect", False)
            continue
        found = "\n".join(introspect_names(board, S1G_SVC, obj))
        checks.lacks(f"{obj} exports no stock-named interface", found, STOCK_NAMED)
        checks.has(f"{obj} exports s1g-named interfaces", found, rf"^{re.escape(S1G_SVC)}\.")

    outside = [p for p in re.findall(r"/fi/[^\s]*", tree)
               if not re.fullmatch(r"/fi(/w1(/wpa_supplicant1_s1g.*)?)?", p)]
    checks.eq(f"no object of wpa_supplicant_s1g lives outside {S1G_PATH}", 0, len(outside))
