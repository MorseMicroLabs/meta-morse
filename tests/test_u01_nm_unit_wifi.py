import os
import re

import pytest

from dsup import build

pytestmark = [pytest.mark.unit, pytest.mark.halow, pytest.mark.standard]

UNIT_TESTS = ["test-supplicant-config", "test-devices-wifi"]


@pytest.mark.parametrize("name", UNIT_TESTS)
def test_u01_nm_unit_wifi(name, board, checks, evidence, settings):
    binary = build.unit_test_binary(settings, name)
    if not binary:
        pytest.skip(f"{name} not found: set build_dir or unit_test_dir (see README.md)")
    checks.info(f"  {name}: {binary}")
    certdir = None
    try:
        board.put_file(binary, f"/tmp/{name}")
        with open(binary, "rb") as f:
            m = re.search(rb'/[^"\x00]*/supplicant/tests/certs/test-ca-cert\.pem', f.read())
        if m:
            certdir = os.path.dirname(m.group(0).decode())
            src = settings.unit_test_certs or certdir
            checks.ok(f"certificate fixtures found ({src})", os.path.isdir(src))
            if os.path.isdir(src):
                board.put_dir(src, certdir)
        res = board.run(f"cd /tmp && timeout 180 ./{name} --tap", timeout=240)
        evidence.save(f"{name}.tap", res.out + res.err)
        ok = len(re.findall(r"^ok", res.out, re.M))
        notok = len(re.findall(r"^not ok", res.out, re.M))
        checks.info(f"  {name}: exit {res.rc}, {ok} ok, {notok} not ok")
        checks.eq(f"{name} exit status", 0, res.rc)
        checks.eq(f"{name} failed cases", 0, notok)
        checks.ok(f"{name} ran at least one case", ok > 0)
    finally:
        board.run(f"rm -f /tmp/{name}")
        if certdir:
            board.run(f"rm -rf '{certdir}'")
