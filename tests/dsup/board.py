import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass


@dataclass
class Result:
    rc: int
    out: str
    err: str

    @property
    def ok(self):
        return self.rc == 0


class Board:
    def __init__(self, settings, logger=None):
        self.s = settings
        self.logger = logger or (lambda msg: None)
        self.trace = []                       # every command that was run, for the report
        self.ctl_dir = os.environ.get("DSUP_SSH_CTL_DIR", f"/tmp/dsup-ssh-{os.getuid()}")
        os.makedirs(self.ctl_dir, mode=0o700, exist_ok=True)
        os.chmod(self.ctl_dir, 0o700)
        self._connect_timeout = settings.int("ssh_connect_timeout")

    def ssh_args(self, connect_timeout=None):
        args = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={connect_timeout or self._connect_timeout}",
            "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=6",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={self.ctl_dir}/%C",
            "-o", "ControlPersist=300",
        ]
        return args + self.s.ssh_extra_args()

    def _record(self, text):
        self.trace.append(self.s.redact(text))
        del self.trace[:-500]

    def run(self, cmd, timeout=120, stdin=None, connect_timeout=None):
        self._record(f"$ {cmd}")
        argv = self.ssh_args(connect_timeout) + [self.s.target, cmd]
        try:
            kw = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
            p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, errors="replace", timeout=timeout, **kw)
            res = Result(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            res = Result(124, out, f"timed out after {timeout}s")
        self._record(f"  -> rc={res.rc}")
        return res

    def sh(self, cmd, timeout=120):
        return self.run(cmd, timeout=timeout).out.rstrip("\n")

    def ok(self, cmd, timeout=120):
        return self.run(cmd, timeout=timeout).ok

    def put_text(self, text, remote, mode="755"):
        q = shlex.quote(remote)
        r = self.run(f"cat > {q} && chmod {mode} {q}", stdin=text)
        if not r.ok:
            raise RuntimeError(f"could not write {remote} on the board: {r.err.strip()}")

    def put_file(self, local, remote, mode="755"):
        with open(local, "rb") as f:
            data = f.read()
        q = shlex.quote(remote)
        argv = self.ssh_args() + [self.s.target, f"cat > {q} && chmod {mode} {q}"]
        p = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(f"could not copy {local} to the board: {p.stderr.decode(errors='replace').strip()}")

    def put_dir(self, local_dir, remote_dir):
        """Copy the contents of a local directory into <remote_dir> (created if needed) with tar."""
        q = shlex.quote(remote_dir)
        tar = subprocess.run(["tar", "-C", str(local_dir), "-cf", "-", "."], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=120)
        if tar.returncode != 0:
            raise RuntimeError(f"could not pack {local_dir}: {tar.stderr.decode(errors='replace').strip()}")
        argv = self.ssh_args() + [self.s.target, f"mkdir -p {q} && tar -C {q} -xf -"]
        p = subprocess.run(argv, input=tar.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(f"could not copy {local_dir} to the board: {p.stderr.decode(errors='replace').strip()}")

    def get_text(self, remote):
        return self.run(f"cat {shlex.quote(remote)} 2>/dev/null").out

    def now(self):
        return self.sh("date '+%Y-%m-%d %H:%M:%S'")

    def uptime_s(self):
        return float(self.sh("cut -d' ' -f1 /proc/uptime") or 0)

    def log(self, msg):
        self.logger(msg)

    def wait_for(self, cmd, timeout, desc, interval=2):
        t0 = time.monotonic()
        while True:
            waited = time.monotonic() - t0
            if self.ok(cmd, timeout=60):
                self.log(f"  ok: {desc} after {waited:.0f}s")
                return True, waited
            if waited >= timeout:
                self.log(f"  TIMEOUT after {timeout}s waiting for: {desc}")
                return False, waited
            time.sleep(interval)

    def reset_connection(self):
        subprocess.run(self.ssh_args() + ["-O", "exit", self.s.target],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    def wait_ssh(self, timeout):
        t0 = time.monotonic()
        self.reset_connection()
        while True:
            waited = time.monotonic() - t0
            try:
                p = subprocess.run(self.ssh_args(connect_timeout=10) + [self.s.target, "true"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=40)
                if p.returncode == 0:
                    return True, waited
            except subprocess.TimeoutExpired:
                pass
            if waited >= timeout:
                return False, waited
            time.sleep(5)


REQUIRED_TOOLS = ("systemctl", "journalctl", "busctl", "nmcli", "timeout", "ping")
REQUIRED_UNITS = ("NetworkManager", "wpa_supplicant", "wpa_supplicant_s1g")


class PreflightError(Exception):
    """PreflightError"""


def missing_settings(s):
    """Names of the required settings that have no value."""
    need = ["device", "s1g_ssid", "std_ssid"]
    if s.s1g_key_mgmt != "none":
        need.append("s1g_key")
    if s.std_key_mgmt != "none":
        need.append("std_key")
    return [n for n in need if not getattr(s, n)]


def preflight(board):
    s = board.s
    missing = missing_settings(s)
    if missing:
        raise PreflightError(
            "These required settings are empty: " + ", ".join(missing) + "\n"
            "  The tests need the board address and, for each radio, an SSID\n"
            "  and its password. Set them in dsup.ini, with DSUP_<NAME> environment variables\n"
            "  or with --dsup-<name> options (--dsup-s1g-ssid).\n"
            "  See README.md, step 3.")
    r = board.run("echo ready", timeout=max(60, s.int("ssh_connect_timeout") * 2))
    if not r.ok or r.out.strip() != "ready":
        detail = (r.err or r.out).strip() or "no answer"
        raise PreflightError(
            f"Cannot log in to the board as {s.target} with ssh.\n"
            f"  ssh said: {detail}\n"
            "  Check the address, that you can ssh to it without typing a password (a key or an\n"
            "  agent is needed), and the 'ssh_options' settings. For a slow link\n"
            "  raise 'ssh_connect_timeout'. See README.md, Troubleshooting.")
    if board.sh("id -u") != "0":
        who = board.sh("id -un")
        raise PreflightError(
            f"You are logged in as '{who}', not root. The tests restart services and change\n"
            "  kernel settings, which needs root. Set 'user = root'.")
    missing = [t for t in REQUIRED_TOOLS if not board.ok(f"command -v {t} >/dev/null")]
    if missing:
        raise PreflightError("These programs are missing on the board: " + ", ".join(missing))
    absent = [u for u in REQUIRED_UNITS
              if board.sh(f"systemctl show -p LoadState --value {u}.service") != "loaded"]
    if absent:
        raise PreflightError("These systemd services are not installed on the board: " + ", ".join(absent))
    if board.sh("systemctl is-active NetworkManager") != "active":
        raise PreflightError("NetworkManager is not running on the board. Start it "
                             "('systemctl start NetworkManager') and run the tests again.")
    for dev in (s.s1g_device, s.std_device):
        if not board.ok(f"[ -d /sys/class/net/{dev} ]"):
            raise PreflightError(f"The board has no network interface '{dev}'. "
                                 "Set 's1g_device' / 'std_device' to the right names.")
    # our own ssh session must not run over a radio that the tests disturb
    conn = board.sh("echo $SSH_CONNECTION")
    parts = conn.split()
    if len(parts) >= 3:
        for dev in (s.s1g_device, s.std_device):
            if board.ok(f"ip -o addr show dev {dev} | grep -qw {shlex.quote(parts[2])}"):
                raise PreflightError(
                    f"Your ssh session to the board runs over {dev}, a radio the tests switch off.\n"
                    "  Use another way in (wired ethernet, for example) so the tests do not cut\n"
                    "  their own connection.")
    facts = {
        "NetworkManager": board.sh("NetworkManager --version"),
        "kernel": board.sh("uname -r"),
        "uptime": board.sh("awk '{printf \"%.1f days\", $1/86400}' /proc/uptime"),
        "boot_id": board.sh("cut -c1-8 /proc/sys/kernel/random/boot_id"),
        "NetworkManager pid": board.sh("systemctl show -p MainPID --value NetworkManager"),
        "wpa_supplicant_s1g Restart=": board.sh("systemctl show -p Restart --value wpa_supplicant_s1g"),
    }
    return facts
