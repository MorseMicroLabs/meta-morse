import shlex
from dataclasses import dataclass

from . import journal
from .supplicant import S1G_PATH, S1G_SVC, STOCK_PATH, STOCK_SVC


@dataclass
class Radio:
    name: str            # "halow" or "standard"
    dev: str             # wlan0 / wlan1
    unit: str            # systemd unit of its supplicant
    svc: str             # D-Bus name of its supplicant
    path: str            # D-Bus root path of its supplicant
    ssid: str = ""
    key: str = ""
    key_mgmt: str = ""
    pmf: str = ""
    conn: str = ""       # NetworkManager connection name (detected unless configured)
    gateway: str = ""    # detected unless configured
    provisioned: bool = False

    @property
    def profile(self):
        return f"dsup-{self.name}"


def make_radios(s):
    halow = Radio("halow", s.s1g_device, "wpa_supplicant_s1g", S1G_SVC, S1G_PATH,
                  s.s1g_ssid, s.s1g_key, s.s1g_key_mgmt, s.s1g_pmf, s.s1g_connection, s.s1g_gateway)
    standard = Radio("standard", s.std_device, "wpa_supplicant", STOCK_SVC, STOCK_PATH,
                     s.std_ssid, s.std_key, s.std_key_mgmt, s.std_pmf, s.std_connection, s.std_gateway)
    return halow, standard


def pid(board):
    return board.sh("systemctl show -p MainPID --value NetworkManager")


def restarts(board):
    return board.sh("systemctl show -p NRestarts --value NetworkManager")


def unit_state(board, unit):
    return board.sh(f"systemctl is-active {unit} 2>/dev/null")


def state(board, ifname):
    return board.sh(f"timeout 5 nmcli -t -f DEVICE,STATE device 2>/dev/null | grep '^{ifname}:' | cut -d: -f2")


def set_managed(board, ifname, managed):
    board.run(f"nmcli device set {ifname} managed {'yes' if managed else 'no'}")


def connected_cmd(*ifnames):
    return " && ".join(
        f"timeout 5 nmcli -t -f DEVICE,STATE device | grep -q '^{i}:connected$'" for i in ifnames)


def wait_connected(board, ifname, timeout):
    return board.wait_for(connected_cmd(ifname), timeout, f"{ifname} connected")


def set_trace_logging(board):
    board.run("nmcli general logging level TRACE domains SUPPLICANT,DEVICE,WIFI")


def set_default_logging(board):
    board.run("nmcli general logging level INFO domains ALL")


def active_connection(board, ifname):
    return board.sh(f"nmcli -g GENERAL.CONNECTION device show {ifname} 2>/dev/null")


def gateway_of(board, ifname):
    lines = board.sh(f"nmcli -g IP4.GATEWAY device show {ifname} 2>/dev/null").splitlines()
    return lines[0].strip() if lines else ""


def delete_wifi_connections(board):
    for line in board.sh("nmcli -t -f UUID,TYPE connection show").splitlines():
        uuid, _, kind = line.partition(":")
        if uuid and kind == "802-11-wireless":
            board.run(f"nmcli connection delete uuid {uuid}")


def provision(board, r):
    board.run(f"nmcli connection delete {r.profile}")
    cmd = ["nmcli", "connection", "add", "type", "wifi", "ifname", r.dev, "con-name", r.profile,
           "ssid", r.ssid, "connection.autoconnect", "yes", "connection.autoconnect-priority", "100"]
    if r.key_mgmt and r.key_mgmt != "none":
        cmd += ["wifi-sec.key-mgmt", r.key_mgmt]
        if r.key:
            cmd += ["wifi-sec.psk", r.key]
        if r.pmf != "":
            cmd += ["wifi-sec.pmf", r.pmf]
    res = board.run(shlex.join(cmd))
    if not res.ok:
        raise RuntimeError(f"could not create the connection for {r.ssid} on {r.dev}: {res.err.strip() or res.out.strip()}")
    r.provisioned = True
    r.conn = r.profile
    board.run(f"nmcli connection up {r.profile} ifname {r.dev}", timeout=120)


def deprovision(board, r):
    if r.provisioned:
        board.run(f"nmcli connection delete {r.profile}")
        r.provisioned = False


def detect(board, r, timeout):
    ok, _ = wait_connected(board, r.dev, timeout)
    if not ok:
        return False
    if not r.conn:
        r.conn = active_connection(board, r.dev)
    if not r.gateway:
        r.gateway = gateway_of(board, r.dev)
    return True


def restore_baseline(board, radios, timeout):
    halow, standard = radios
    board.log("restoring baseline")
    board.run(
        "systemctl reset-failed NetworkManager wpa_supplicant wpa_supplicant_s1g 2>/dev/null; "
        "for u in wpa_supplicant wpa_supplicant_s1g NetworkManager; do "
        "systemctl is-active -q $u || systemctl start $u; done; sleep 3; "
        f"nmcli device set {halow.dev} managed yes; nmcli device set {standard.dev} managed yes; "
        "nmcli general logging level TRACE domains SUPPLICANT,DEVICE,WIFI; true",
        timeout=180)
    ok, _ = board.wait_for(connected_cmd(halow.dev, standard.dev), timeout,
                           f"{halow.dev} and {standard.dev} connected")
    return ok


class Health:
    def __init__(self, board):
        self.board = board
        self.pid = self.restarts = self.since = None
        self.armed = False       # a snapshot was taken
        self.checked = False     # ... and it was checked since

    def snapshot(self):
        self.pid = pid(self.board)
        self.restarts = restarts(self.board)
        self.since = self.board.now()
        self.armed, self.checked = True, False

    def check(self, checks, evidence=None, name="health.log"):
        text = journal.nm_journal(self.board, self.since)
        if evidence is not None:
            evidence.save(name, text)
        checks.eq("NetworkManager was not restarted by systemd", self.restarts, restarts(self.board))
        checks.eq("NetworkManager main pid is unchanged", self.pid, pid(self.board))
        checks.lacks("no SIGSEGV in the journal", text, journal.SEGV_PATTERN)
        checks.lacks("no GLib assertion/critical from NetworkManager", text, journal.GLIB_PATTERN)
        self.checked = True
        return text


def first_attempt_checks(checks, nm_log, halow_dev, bus_text=None):
    from . import bus
    checks.lacks("no \"Couldn't initialize supplicant interface\"", nm_log, "Couldn't initialize supplicant interface")
    checks.lacks("no \"name owner changed\"", nm_log, "name owner changed")
    checks.lacks("wlan0 never fell back with 'supplicant-failed' (no retry)", nm_log,
                 rf"device \({halow_dev}\): state change: .*reason 'supplicant-failed'")
    if bus_text is not None:
        checks.count_eq("exactly one CreateInterface sent to wpa_supplicant_s1g (no retry)", 1,
                        bus_text, bus.s1g_call("CreateInterface"))
        checks.lacks("no D-Bus error from the s1g supplicant", bus_text, "ErrorName=fi.w1.wpa_supplicant1_s1g")
