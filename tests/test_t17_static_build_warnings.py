import os
import re

import pytest

from dsup import build

pytestmark = [pytest.mark.host]

SUPPLICANT_WARNING = re.compile(r"supplicant/nm-supplicant-(interface|manager)\.c:\d+:\d+: warning")


def _warnings(path):
    out = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if ": warning: " in line:
                line = re.sub(r"^.*/(src|libnm|shared)/", r"\1/", line.rstrip())
                out.add(re.sub(r":\d+:\d+: ", ": ", line))
    return out


def test_t17_static_build_warnings(settings, checks, evidence):
    clog = build.compile_log(settings)
    if not clog or not os.path.exists(clog):
        pytest.skip("no NetworkManager compile log: set compile_log or build_dir (see README.md)")
    checks.info(f"  compile log: {clog}")
    with open(clog, encoding="utf-8", errors="replace") as f:
        ours = [ln.rstrip() for ln in f if SUPPLICANT_WARNING.search(ln)]
    evidence.save("warnings.txt", "\n".join(ours))
    text = "\n".join(ours)
    checks.eq("maybe-uninitialized warnings in the supplicant code", 0, text.count("maybe-uninitialized"))
    checks.eq("unused-variable warnings in the supplicant code", 0, text.count("Wunused"))
    checks.eq("declaration-after-statement warnings in the supplicant code (new compared with upstream)", 0,
              text.count("Wdeclaration-after-statement"))
    other = [ln for ln in ours if not re.search("maybe-uninitialized|Wunused|Wdeclaration-after-statement", ln)]
    checks.eq("any other warning in the supplicant code", 0, len(other))

    if settings.baseline_log:
        checks.ok("found the baseline compile log", os.path.exists(settings.baseline_log))
        if os.path.exists(settings.baseline_log):
            new = sorted(_warnings(clog) - _warnings(settings.baseline_log))
            evidence.save("warnings_new.txt", "\n".join(new))
            checks.eq("warnings (any file) that the unpatched baseline build does not have", 0, len(new))
    else:
        checks.info("  no baseline_log: warnings outside the supplicant files were not compared with an unpatched build")
