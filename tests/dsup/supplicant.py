import re
import shlex

S1G_SVC = "fi.w1.wpa_supplicant1_s1g"
S1G_PATH = "/fi/w1/wpa_supplicant1_s1g"
STOCK_SVC = "fi.w1.wpa_supplicant1"
STOCK_PATH = "/fi/w1/wpa_supplicant1"


def _quoted_strings(text):
    return re.findall(r'"([^"]*)"', text)


def interfaces(board, svc, path):
    out = board.sh(f"busctl get-property {svc} {path} {svc} Interfaces 2>/dev/null")
    return _quoted_strings(out)


def s1g_interfaces(board):
    return interfaces(board, S1G_SVC, S1G_PATH)


def stock_interfaces(board):
    return interfaces(board, STOCK_SVC, STOCK_PATH)


def s1g_iface_count(board):
    return len(s1g_interfaces(board))


def s1g_remove_all_interfaces(board):
    for p in s1g_interfaces(board):
        board.run(f"busctl call {S1G_SVC} {S1G_PATH} {S1G_SVC} RemoveInterface o {shlex.quote(p)}")


def interface_for(board, svc, path, ifname):
    for p in interfaces(board, svc, path):
        out = board.sh(f"busctl get-property {svc} {p} {svc}.Interface Ifname")
        if _quoted_strings(out)[:1] == [ifname]:
            return p
    return None


def introspect_names(board, svc, path):
    out = board.sh(f"busctl call {svc} {path} org.freedesktop.DBus.Introspectable Introspect 2>/dev/null")
    return sorted(set(re.findall(r"fi\.w1\.wpa_supplicant1[A-Za-z0-9_.]*", out)))


def bus_names(board):
    out = {}
    for line in board.sh("busctl --no-pager list").splitlines():
        cols = line.split()
        if len(cols) >= 5 and cols[1].isdigit():
            out[cols[0]] = (int(cols[1]), cols[4])
    return out
