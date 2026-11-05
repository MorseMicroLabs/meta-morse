import glob
import os


def newest(pattern):
    hits = glob.glob(pattern)
    return max(hits, key=os.path.getmtime) if hits else None


def work_glob(build_dir, *parts):
    return os.path.join(build_dir, "tmp", "work", "*", *parts)


def compile_log(s):
    if s.compile_log:
        return s.compile_log
    if s.build_dir:
        return newest(work_glob(s.build_dir, "networkmanager", "*", "temp", "log.do_compile"))
    return None


def unit_test_binary(s, name):
    if s.unit_test_dir:
        p = os.path.join(s.unit_test_dir, name)
        return p if os.path.exists(p) else None
    if not s.build_dir:
        return None
    for top in ("build", "networkmanager-*"):
        for sub in ("src/core/supplicant/tests", "src/core/devices/wifi"):
            p = newest(work_glob(s.build_dir, "networkmanager", "*", top, sub, name))
            if p:
                return p
    return None


def download_dir(s):
    if s.dl_dir:
        return s.dl_dir
    if s.build_dir:
        cand = os.path.join(os.path.dirname(os.path.abspath(s.build_dir)), "downloads")
        if os.path.isdir(cand):
            return cand
    return None


def hostap_worktree(s):
    if s.build_dir:
        return newest(work_glob(s.build_dir, "morse-wpa-supplicant", "*", "git"))
    return None
