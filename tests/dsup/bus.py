import re
import shlex
from calendar import timegm
from datetime import datetime

from .supplicant import S1G_PATH, S1G_SVC, STOCK_PATH, STOCK_SVC

_TS = re.compile(r'Timestamp="[A-Za-z]{3} (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(\.\d+)?')
_FIELD = re.compile(r'(\w+)=("[^"]*"|\S+)')


def call_pattern(member, svc=S1G_SVC, path=S1G_PATH):
    return rf"Path={re.escape(path)} +Interface={re.escape(svc)} +Member={member}\b"


def s1g_call(member):
    return call_pattern(member, S1G_SVC, S1G_PATH)


def stock_call(member):
    return call_pattern(member, STOCK_SVC, STOCK_PATH)


def parse_epoch(timestamp_line):
    m = _TS.search(timestamp_line)
    if not m:
        return None
    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    return timegm(dt.timetuple()) + (float(m.group(2)) if m.group(2) else 0.0)


def messages(text):
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("> Type="):
            cur = {"epoch": parse_epoch(line), "fields": dict(_FIELD.findall(line)), "strings": []}
            out.append(cur)
        elif cur is not None:
            if re.match(r"^ {2}\w+=", line):                 # header continuation (Sender=..., Member=...)
                for k, v in _FIELD.findall(line):
                    cur["fields"].setdefault(k, v)
            else:
                m = re.match(r'^\s+STRING "(.*)";?$', line)
                if m:
                    cur["strings"].append(m.group(1))
    return out


def owner_appeared(text, service):
    for m in messages(text):
        f = m["fields"]
        if f.get("Member") == "NameOwnerChanged" and len(m["strings"]) >= 3:
            name, _old, new = m["strings"][:3]
            if name == service and new:
                return m["epoch"]
    return None


def start_service_calls(text, service):
    out = []
    for m in messages(text):
        if m["fields"].get("Member") == "StartServiceByName" and m["strings"][:1] == [service]:
            out.append((m["epoch"], m["fields"].get("Sender")))
    return out


def first_signal_epoch(text, interface, member):
    for m in messages(text):
        f = m["fields"]
        if f.get("Interface") == interface and f.get("Member") == member:
            return m["epoch"]
    return None


class BusCapture:
    def __init__(self, board, tag="bus"):
        self.board = board
        self.remote = f"/tmp/dsup_{tag}.txt"
        self.pidfile = f"/tmp/dsup_{tag}.pid"
        self.text = ""
        self._running = False

    def start(self):
        r, p = shlex.quote(self.remote), shlex.quote(self.pidfile)
        self.board.run(
            f"rm -f {r} {p}; (timeout 900 busctl --system monitor --no-pager > {r} 2>&1 & echo $! > {p}); sleep 1")
        self._running = True
        return self

    def stop(self):
        if self._running:
            self.board.run(f"kill $(cat {shlex.quote(self.pidfile)}) 2>/dev/null; sleep 1")
            self.text = self.board.get_text(self.remote)
            self.board.run(f"rm -f {shlex.quote(self.remote)} {shlex.quote(self.pidfile)}")
            self._running = False
        return self.text

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
