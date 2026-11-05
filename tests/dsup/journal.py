import re
import shlex

NM_FILTER = r"NetworkManager|wpa_supplicant|systemd\[1\]: .*(NetworkManager|wpa_supplicant)|segfault|SEGV"

CRASH_FILTER = (
    r"NetworkManager\.service: (Main process exited, code=(dumped|killed)|Failed with result .(core-dump|signal))"
    r"|wpa_supplicant(_s1g)?\.service: Main process exited, code=dumped"
    r"|segfault at [0-9a-f]+ ip .*(NetworkManager|wpa_supplicant)"
    r"|Process [0-9]+ \((NetworkManager|wpa_supplicant[a-z0-9_]*)\) of .* dumped core"
)

SEGV_PATTERN = r"status=11/SEGV|segfault|code=dumped"
GLIB_PATTERN = r"NetworkManager\[[0-9]+\]: (g_|\*\* |.*assertion .* failed|.*CRITICAL)"

_NM_STAMP = re.compile(r"\[(\d{10}\.\d+)\]")


def journal_since(board, since, pattern=NM_FILTER, unit=None):
    u = f"-u {unit} " if unit else ""
    return board.sh(
        f"journalctl -b --no-pager {u}--since {shlex.quote(since)} 2>/dev/null | grep -E {shlex.quote(pattern)}",
        timeout=180)


def nm_journal(board, since):
    return journal_since(board, since, NM_FILTER)


def crash_lines(board, since):
    return journal_since(board, since, CRASH_FILTER)


def core_files(board, core_dir):
    out = board.sh(f"ls -l {shlex.quote(core_dir)} 2>/dev/null | grep -v '^total'")
    return [ln for ln in out.splitlines() if ln.strip()]


def nm_epoch(line):
    m = _NM_STAMP.search(line)
    return float(m.group(1)) if m else None


def log_after_epoch(text, epoch):
    keep = []
    for line in text.splitlines():
        e = nm_epoch(line)
        if e is not None and e < epoch:
            continue
        keep.append(line)
    return "\n".join(keep)


def activation_epochs(text, ifname):
    pat = re.compile(r"device \(" + re.escape(ifname) + r"\): state change: .* -> activated")
    out = []
    for line in text.splitlines():
        if pat.search(line):
            e = nm_epoch(line)
            if e is not None:
                out.append(e)
    return out


def first_activation_after(board, ifname, since, epoch):
    text = journal_since(board, since, rf"device \({re.escape(ifname)}\): state change: .* -> activated",
                         unit="NetworkManager")
    for e in activation_epochs(text, ifname):
        if e >= epoch:
            return e
    return None


def wait_activated_after(board, ifname, since, epoch, timeout, interval=3):
    import time
    t0 = time.monotonic()
    while True:
        e = first_activation_after(board, ifname, since, epoch)
        if e is not None:
            return e
        if time.monotonic() - t0 >= timeout:
            return None
        time.sleep(interval)
