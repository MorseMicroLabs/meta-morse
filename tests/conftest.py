"""pytest set-up for the dual-supplicant tests.

Options, the `settings` / `board` / `checks` / `evidence` fixtures, the report hooks.
"""
import html
import re
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from dsup import config as cfg
from dsup import journal
from dsup import nm as nmmod
from dsup.board import Board, PreflightError, preflight
from dsup.checks import Checks

CHECKS_KEY = pytest.StashKey[Checks]()


def pytest_addoption(parser):
    g = parser.getgroup("dsup", "dual-supplicant tests")
    g.addoption("--dsup-config", dest="dsup_config", default=None,
                help="settings file (default: $DSUP_CONFIG, or dsup.ini next to this file)")
    g.addoption("--run-disruptive", action="store_true", default=False,
                help="also run the tests that reboot the board")
    for s in cfg.SETTINGS:
        g.addoption(cfg.option_name(s.name), dest=cfg.dest_name(s.name), default=None,
                    metavar="VALUE", help=f"{s.help} [env {cfg.env_name(s.name)}]")


def _resolve_settings(config):
    cli = {s.name: config.getoption(cfg.dest_name(s.name)) for s in cfg.SETTINGS}
    try:
        return cfg.resolve(cli=cli, ini_path=config.getoption("dsup_config"))
    except (OSError, ValueError) as e:
        raise pytest.UsageError(f"cannot read the settings: {e}") from e


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config._dsup_settings = _resolve_settings(config)
    s = config._dsup_settings
    results = Path(s.results_dir)
    if hasattr(config.option, "htmlpath") and not config.option.htmlpath:
        config.option.htmlpath = str(results / "report.html")
        if hasattr(config.option, "self_contained_html"):
            config.option.self_contained_html = True
    if hasattr(config.option, "xmlpath") and not config.option.xmlpath:
        config.option.xmlpath = str(results / "junit.xml")
    config._dsup_board = None
    config._dsup_checks = None
    config._dsup_guard = None
    config._dsup_facts = {}


def pytest_report_header(config):
    s = config._dsup_settings
    lines = ["dsup settings that differ from the defaults:"]
    lines += ["  " + ln for ln in s.describe()] or ["  (none)"]
    return lines


def pytest_collection_modifyitems(config, items):
    run_disruptive = config.getoption("--run-disruptive")
    skip_dis = pytest.mark.skip(reason="reboots the board: run it with --run-disruptive")
    for item in items:
        if not item.get_closest_marker("host"):
            item.add_marker(pytest.mark.board)
        if item.get_closest_marker("disruptive") and not run_disruptive:
            item.add_marker(skip_dis)


@pytest.fixture(scope="session")
def settings(request):
    return request.config._dsup_settings


@pytest.fixture(scope="session")
def results_dir(settings):
    d = Path(settings.results_dir)
    ev = d / "evidence"
    if ev.exists():
        shutil.rmtree(ev, ignore_errors=True)
    ev.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def board(request, settings, results_dir):
    b = Board(settings)
    try:
        facts = preflight(b)
    except PreflightError as e:
        pytest.exit(f"\nPREFLIGHT FAILED\n{e}\n", returncode=2)
    request.config._dsup_board = b
    request.config._dsup_facts = facts
    b.logger = lambda msg: (request.config._dsup_checks or Checks()).info(msg)
    try:
        from pytest_metadata.plugin import metadata_key
        meta = request.config.stash[metadata_key]
        meta["Board"] = settings.target
        for k, v in facts.items():
            meta[k] = v
    except Exception:
        pass
    (results_dir / "environment.txt").write_text(
        "".join(f"{k}: {v}\n" for k, v in [("board", settings.target), *facts.items()]), encoding="utf-8")
    return b


@pytest.fixture(autouse=True)
def checks(request, settings):
    c = Checks(redact=settings.redact)
    request.node.stash[CHECKS_KEY] = c
    request.config._dsup_checks = c
    if request.config._dsup_board is not None:
        request.config._dsup_board.trace.clear()
    yield c


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


class Evidence:
    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)

    def save(self, name, text):
        (self.path / name).write_text(text if isinstance(text, str) else str(text), encoding="utf-8")
        return self.path / name


@pytest.fixture
def evidence(request, results_dir):
    return Evidence(results_dir / "evidence" / _safe(request.node.name))


def _is_host(request):
    return request.node.get_closest_marker("host") is not None

@pytest.fixture(scope="session")
def radios(request, board, settings):
    pair = nmmod.make_radios(settings)
    timeout = settings.int("connect_timeout")
    try:
        nmmod.delete_wifi_connections(board)
        for r in pair:
            nmmod.provision(board, r)
        for r in pair:
            if not nmmod.detect(board, r, timeout):
                raise RuntimeError(
                    f"{r.dev} is not connected after {timeout} s. Give the tests an access point "
                    f"(settings {'s1g' if r.name == 'halow' else 'std'}_ssid and "
                    f"{'s1g' if r.name == 'halow' else 'std'}_key), or connect it yourself first.")
    except RuntimeError as e:
        for r in pair:
            nmmod.deprovision(board, r)
        pytest.exit(f"\nSET-UP FAILED\n{e}\n", returncode=2)
    yield pair


@pytest.fixture
def radio(request, radios):
    return radios[0] if request.param == "halow" else radios[1]


@pytest.fixture(scope="session")
def halow(radios):
    return radios[0]


@pytest.fixture(scope="session")
def standard(radios):
    return radios[1]


@dataclass
class RunGuard:
    since: str
    nm_pid: str
    original_core_pattern: str
    core_dir: str
    crashes: list = field(default_factory=list)
    cores: list = field(default_factory=list)
    finished: bool = False

    @property
    def failed(self):
        return bool(self.crashes or self.cores)


@pytest.fixture(scope="session", autouse=True)
def run_guard(request, settings):
    if all(i.get_closest_marker("host") for i in request.session.items):
        yield None
        return
    board = request.getfixturevalue("board")
    radios = request.getfixturevalue("radios")
    results_dir = request.getfixturevalue("results_dir")
    core_dir = settings.core_dir
    orig = board.sh("cat /proc/sys/kernel/core_pattern")
    board.run(f"mkdir -p {shlex.quote(core_dir)} && rm -f {shlex.quote(core_dir)}/* && "
              f"echo {shlex.quote(core_dir + '/core.%e.%p')} > /proc/sys/kernel/core_pattern")
    guard = RunGuard(board.now(), nmmod.pid(board), orig, core_dir)
    request.config._dsup_guard = guard
    yield guard
    try:
        guard.crashes = [ln for ln in journal.crash_lines(board, guard.since).splitlines() if ln.strip()]
        guard.cores = journal.core_files(board, core_dir)
        guard.finished = True
        (results_dir / "run_crashes.txt").write_text("\n".join(guard.crashes) + "\n", encoding="utf-8")
        (results_dir / "run_cores.txt").write_text("\n".join(guard.cores) + "\n", encoding="utf-8")
    finally:
        # leave the board as we found it
        board.run(f"printf '%s\\n' {shlex.quote(orig)} > /proc/sys/kernel/core_pattern")
        nmmod.restore_baseline(board, radios, settings.int("connect_timeout"))
        nmmod.set_default_logging(board)


@pytest.fixture
def restore(request, board, radios, settings):
    return lambda: nmmod.restore_baseline(board, radios, settings.int("connect_timeout"))


@pytest.fixture(autouse=True)
def health(request, checks):
    if _is_host(request):
        yield None
        return
    board = request.getfixturevalue("board")
    radios = request.getfixturevalue("radios")
    settings = request.getfixturevalue("settings")
    if not nmmod.restore_baseline(board, radios, settings.int("connect_timeout")):
        pytest.fail("could not bring the board back to the baseline (both radios connected) "
                    "before the test; the test was not run", pytrace=False)
    h = nmmod.Health(board)
    h.snapshot()
    yield h


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    yield
    h = item.funcargs.get("health")
    c = item.stash.get(CHECKS_KEY, None)
    if h is not None and c is not None and h.armed and not h.checked:
        try:
            c.info("end of test: NetworkManager health")
            h.check(c)
        except Exception as e:      # a board that cannot be reached is reported, not hidden
            c.ok(f"NetworkManager health check could not run: {e}", False)


def pytest_sessionfinish(session, exitstatus):
    g = session.config._dsup_guard
    if g is not None and g.finished and g.failed and session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config):
    g = config._dsup_guard
    if g is None or not g.finished:
        return
    tr = terminalreporter
    tr.section("run-wide crash check")
    tr.write_line(f"crashes of NetworkManager or the supplicants in the journal during the run: {len(g.crashes)}")
    tr.write_line(f"core files written during the run: {len(g.cores)}")
    for ln in g.crashes[:10] + g.cores[:10]:
        tr.write_line("  " + ln[:200], red=True)
    tr.write_line("RESULT: " + ("FAIL (see results/run_crashes.txt and run_cores.txt)" if g.failed else "ok"),
                  red=g.failed, green=not g.failed)


def pytest_html_report_title(report):
    report.title = "Dual-supplicant test report"


def pytest_html_results_summary(prefix, summary, postfix, session):
    g = session.config._dsup_guard
    if g is None or not g.finished:
        return
    verdict = "FAIL" if g.failed else "ok"
    prefix.extend([
        f"<p><b>Run-wide crash check: {verdict}.</b> Crashes in the journal: {len(g.crashes)}. "
        f"Core files: {len(g.cores)}.</p>"])
    if g.failed:
        prefix.extend(["<pre>" + html.escape("\n".join(g.crashes + g.cores)) + "</pre>"])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    c = item.stash.get(CHECKS_KEY, None)
    if c is None:
        return
    if c.failures and rep.passed:
        rep.outcome = "failed"
        rep.longrepr = c.failure_text()
    elif c.failures and rep.failed:
        rep.sections.append(("failed checks", c.failure_text()))
    if c.lines:
        rep.sections.append(("checks and log", c.render()))
    b = item.config._dsup_board
    if b is not None and rep.failed and b.trace:
        rep.sections.append(("last commands on the board", "\n".join(b.trace[-60:])))
