import shlex

PING_SH = """#!/bin/sh
# pingmon.sh <ifname> <gateway> <outfile>  - one probe per second, "<uptime> ok|lost"
IF=$1; GW=$2; OUT=$3
: > $OUT
while :; do
    if ping -I $IF -c1 -W1 $GW >/dev/null 2>&1; then R=ok; else R=lost; fi
    echo "$(cut -d' ' -f1 /proc/uptime) $R" >> $OUT
    sleep 1
done
"""

STATE_SH = """#!/bin/sh
# statemon.sh <ifname> <outfile>  - one sample per second, "<uptime> <NetworkManager state> <link state>"
# The link state comes from the kernel, so it is known even when NetworkManager is too busy to answer.
IF=$1; OUT=$2
: > $OUT
while :; do
    S=$(timeout 3 nmcli -t -f DEVICE,STATE device 2>/dev/null | grep "^$IF:" | cut -d: -f2)
    L=$(cat /sys/class/net/$IF/operstate 2>/dev/null)
    echo "$(cut -d' ' -f1 /proc/uptime) ${S:-nm-unreachable} ${L:-unknown}" >> $OUT
    sleep 1
done
"""


class _Monitor:
    script = ""
    script_name = ""

    def __init__(self, board, tag, *args):
        self.board = board
        self.tag = tag
        self.args = args
        self.out = f"/tmp/dsup_{self.script_name}_{tag}.txt"
        self.pidfile = f"/tmp/dsup_{self.script_name}_{tag}.pid"
        self.text = ""
        self._running = False

    def start(self):
        script = f"/tmp/dsup_{self.script_name}.sh"
        self.board.put_text(self.script, script)
        a = " ".join(shlex.quote(x) for x in self.args)
        self.board.run(f"rm -f {self.pidfile}; ({script} {a} {self.out} >/dev/null 2>&1 & echo $! > {self.pidfile})")
        self._running = True
        return self

    def stop(self):
        if self._running:
            self.board.run(f"kill $(cat {self.pidfile}) 2>/dev/null")
            self.text = self.board.get_text(self.out)
            self.board.run(f"rm -f {self.out} {self.pidfile} /tmp/dsup_{self.script_name}.sh")
            self._running = False
        return self

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    @property
    def lines(self):
        return [ln for ln in self.text.splitlines() if ln.strip()]


class PingMonitor(_Monitor):
    script, script_name = PING_SH, "pingmon"

    def __init__(self, board, tag, ifname, gateway):
        super().__init__(board, tag, ifname, gateway)

    @property
    def ok(self):
        return sum(1 for ln in self.lines if ln.endswith(" ok"))

    @property
    def lost(self):
        return sum(1 for ln in self.lines if ln.endswith(" lost"))

    @property
    def longest_lost_run(self):
        """The most probes lost one after the other (one probe per second, so about seconds of outage)."""
        best = run = 0
        for ln in self.lines:
            run = run + 1 if ln.endswith(" lost") else 0
            best = max(best, run)
        return best


class StateMonitor(_Monitor):
    script, script_name = STATE_SH, "statemon"

    def __init__(self, board, tag, ifname):
        super().__init__(board, tag, ifname)

    @property
    def samples(self):
        return len(self.lines)

    def _fields(self):
        return [ln.split() for ln in self.lines]

    @property
    def not_connected(self):
        """Samples in which the radio was really not connected: NetworkManager said so, or the kernel
        reported the link as not up. A sample where NetworkManager did not answer does not count."""
        n = 0
        for f in self._fields():
            nm_state = f[1] if len(f) > 1 else "nm-unreachable"
            link = f[2] if len(f) > 2 else "up"
            if (nm_state not in ("connected", "nm-unreachable")) or link != "up":
                n += 1
        return n

    @property
    def unreachable(self):
        """Samples in which NetworkManager did not answer within 3 s (it was busy, not necessarily down)."""
        return sum(1 for f in self._fields() if len(f) > 1 and f[1] == "nm-unreachable")


SEQUENCE_SH = """#!/bin/sh
# seqmon.sh <ifname> <outfile>  - once per second "<uptime> <NetworkManager pid> <s1g interface count> <state>"
IF=$1; OUT=$2
: > $OUT
while :; do
    PID=$(systemctl show -p MainPID --value NetworkManager)
    N=$(busctl get-property fi.w1.wpa_supplicant1_s1g /fi/w1/wpa_supplicant1_s1g fi.w1.wpa_supplicant1_s1g Interfaces 2>/dev/null | grep -o '"/' | wc -l)
    ST=$(timeout 3 nmcli -t -f DEVICE,STATE device 2>/dev/null | grep "^$IF:" | cut -d: -f2)
    echo "$(cut -d' ' -f1 /proc/uptime) $PID $N ${ST:-none}" >> $OUT
    sleep 1
done
"""


class SequenceMonitor(_Monitor):
    script, script_name = SEQUENCE_SH, "seqmon"

    def __init__(self, board, tag, ifname):
        super().__init__(board, tag, ifname)

    def fetch(self):
        self.text = self.board.get_text(self.out)
        return self.rows()

    def rows(self):
        rows = []
        for ln in self.lines:
            p = ln.split()
            if len(p) >= 4:
                rows.append((float(p[0]), p[1], int(p[2]), p[3]))
        return rows
