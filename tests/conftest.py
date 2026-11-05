"""pytest set-up for the dual-supplicant tests.

Options, the `settings` / `board` / `checks` / `evidence` fixtures, the report hooks.
"""
import os
import re
import shutil
from pathlib import Path

import pytest

from dsup import config as cfg
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
