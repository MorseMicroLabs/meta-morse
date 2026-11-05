import hashlib
import os
import re
import shutil
import subprocess
import urllib.request

import pytest

from dsup import build

pytestmark = [pytest.mark.host]


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "dsup-tests"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def fetch(settings, version, checks):
    """Path of the NetworkManager source tarball for a release, or None."""
    name = f"NetworkManager-{version}.tar.xz"
    dl = build.download_dir(settings)
    for d in (settings.nm_src_dir, dl):
        if d and os.path.isfile(os.path.join(d, name)):
            return os.path.join(d, name)
    if not settings.flag("nm_download"):
        return None
    base = f"https://gitlab.freedesktop.org/NetworkManager/NetworkManager/-/releases/{version}/downloads/"
    os.makedirs(settings.nm_src_dir, exist_ok=True)
    dest = os.path.join(settings.nm_src_dir, name)
    try:
        _download(base + name, dest)
        with urllib.request.urlopen(urllib.request.Request(base + f"NetworkManager-{version}.tar.xz.sha256sum",
                                                           headers={"User-Agent": "dsup-tests"}), timeout=60) as r:
            want = next((ln.split()[0] for ln in r.read().decode().splitlines() if ".tar.xz" in ln), None)
        have = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    except OSError as e:
        checks.info(f"  could not download {name}: {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return None
    if not want or want != have:
        checks.info(f"  checksum of {name} could not be verified (wanted '{want}', got {have}); not used")
        os.remove(dest)
        return None
    return dest


def apply_all(settings, checks, evidence, tmp_path, version):
    tarball = fetch(settings, version, checks)
    checks.ok(f"NetworkManager {version} source available", bool(tarball))
    if not tarball:
        return
    work = tmp_path / f"nm-{version}"
    work.mkdir()
    subprocess.run(["tar", "-C", str(work), "-xf", tarball], check=False, timeout=300)
    src = work / f"NetworkManager-{version}"
    checks.ok(f"NetworkManager {version} unpacked", src.is_dir())
    if not src.is_dir():
        return
    for patch in settings.words("nm_patches"):
        path = os.path.join(settings.patch_dir, patch)
        if not os.path.isfile(path):
            checks.ok(f"{version}: patch file {path} exists", False)
            continue
        with open(path, "rb") as f:
            r = subprocess.run(["patch", "-p1", "--no-backup-if-mismatch"], cwd=src, stdin=f,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        evidence.save(f"patch-{version}-{patch.split('-')[0]}.log", r.stdout)
        checks.ok(f"{version}: {patch} applies", r.returncode == 0)
        checks.lacks(f"{version}: {patch} applies without FAILED hunks", r.stdout, "FAILED|rejects")
        checks.lacks(f"{version}: {patch} applies without fuzz", r.stdout, "fuzz")
        checks.info(f"  {version} {patch}: {len(re.findall('offset', r.stdout))} hunk(s) with an offset")
    shutil.rmtree(work, ignore_errors=True)


def test_t24_patches_apply(settings, checks, evidence, tmp_path):
    for version in settings.words("nm_versions"):
        checks.info(f"NetworkManager {version}")
        apply_all(settings, checks, evidence, tmp_path, version)

    # hostap: what the supplicant recipe builds
    tag = settings.hostap_tag
    recipe = settings.hostap_recipe
    if os.path.isfile(recipe):
        text = open(recipe, encoding="utf-8").read()
        checks.has(f"morse-wpa-supplicant recipe builds tag {tag}", text, rf'^TAG_NAME = "{re.escape(tag)}"')
    else:
        checks.info(f"  recipe {recipe} not found: only the work tree was checked")
    wd = build.hostap_worktree(settings)
    if wd:
        r = subprocess.run(["git", "-C", wd, "describe", "--tags", "--exact-match"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        found = r.stdout.strip()
        checks.info(f"  morse-wpa-supplicant work tree: {found or '(not exactly at a tag)'}")
        checks.eq(f"the built hostap tree is at tag {tag}", tag, found)
    else:
        checks.info("  no morse-wpa-supplicant work tree found (build_dir not set or empty); only the recipe was checked")
