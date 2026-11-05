import configparser
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
LAYER_DIR = TESTS_DIR.parent          # meta-morse

DEFAULT_PATCHES = (
    "0002-patch-configure-networkmanager-to-talk-to-2.patch "
    "0003-supplicant-keep-per-supplicant-state.patch"
)


@dataclass(frozen=True)
class Setting:
    name: str
    default: str
    help: str
    secret: bool = False


SETTINGS = [
    Setting("device", "", "address of the DUT (device under test); required"),
    Setting("user", "root", "login name on the board"),
    Setting("ssh_options", "", "optional extra ssh options, written as on the ssh command line"),
    Setting("ssh_connect_timeout", "30", "seconds to wait when connecting to the board"),
    Setting("s1g_device", "wlan0", "network interface of the HaLow (s1g) radio"),
    Setting("s1g_ssid", "", "access point (SSID) for the HaLow radio; required"),
    Setting("s1g_key", "", "password of the HaLow access point; required", secret=True),
    Setting("s1g_key_mgmt", "sae", "security of the HaLow connection: sae (WPA3) or wpa-psk (WPA2)"),
    Setting("s1g_pmf", "3", "PMF setting of the HaLow connection (nmcli: 0 default, 1 disable, 2 optional, 3 required)"),
    Setting("s1g_connection", "", "name of the HaLow NetworkManager connection (default: detected)"),
    Setting("s1g_gateway", "", "gateway reached over the HaLow radio (default: detected)"),
    Setting("std_device", "wlan1", "network interface of the standard radio"),
    Setting("std_ssid", "", "access point (SSID) for the standard radio; required"),
    Setting("std_key", "", "password of the standard access point; required", secret=True),
    Setting("std_key_mgmt", "sae", "security of the standard connection: sae (WPA3) or wpa-psk (WPA2)"),
    Setting("std_pmf", "3", "PMF setting of the standard connection (nmcli: 0 default, 1 disable, 2 optional, 3 required)"),
    Setting("std_connection", "", "name of the standard NetworkManager connection (default: detected)"),
    Setting("std_gateway", "", "gateway reached over the standard radio (default: detected)"),
    Setting("results_dir", str(TESTS_DIR / "results"), "where the report and the evidence of a run are written"),
    Setting("connect_timeout", "90", "seconds to wait for a radio to be connected again"),
    Setting("recovery_limit", "15", "seconds allowed from s1g owning its name again until wlan0 is up"),
    Setting("core_dir", "/var/volatile/cores", "directory on the board where core dumps are collected during a run"),
    Setting("build_dir", "", "Yocto build directory"),
    Setting("dl_dir", "", "Yocto downloads directory"),
    Setting("compile_log", "", "NetworkManager do_compile log to check for warnings"),
    Setting("baseline_log", "", "do_compile log of an UNPATCHED build, to compare all warnings with"),
    Setting("unit_test_dir", "", "directory with the NetworkManager unit-test binaries"),
    Setting("unit_test_certs", "", "copy of src/core/supplicant/tests/certs of the NetworkManager source"),
    Setting("patch_dir", str(LAYER_DIR / "recipes-connectivity" / "networkmanager"), "directory with the NetworkManager patches"),
    Setting("nm_patches", DEFAULT_PATCHES, "NetworkManager patches to apply, in order"),
    Setting("nm_versions", "1.46.0 1.46.6", "NetworkManager releases the patches must apply to"),
    Setting("nm_src_dir", "/tmp/dsup-nm-src", "where NetworkManager tarballs are kept or downloaded to"),
    Setting("nm_download", "1", "1 = download missing NetworkManager tarballs, 0 = never download"),
    Setting("hostap_tag", "mm8108-2.1.0", "hostap tag the supplicant recipe must build"),
    Setting("hostap_recipe", str(LAYER_DIR / "recipes-morse" / "morse-wpa-supplicant" / "morse-wpa-supplicant.bb"),
            "supplicant recipe that names the hostap tag"),
]
NAMES = {s.name for s in SETTINGS}


def env_name(name):
    return "DSUP_" + name.upper()


def option_name(name):
    return "--dsup-" + name.replace("_", "-")


def dest_name(name):
    return "dsup_" + name


def read_ini(path):
    cp = configparser.ConfigParser(interpolation=None)
    with open(path, encoding="utf-8") as f:
        cp.read_file(f)
    if not cp.has_section("dsup"):
        return {}
    unknown = [k for k in cp["dsup"] if k not in NAMES]
    if unknown:
        raise ValueError(f"{path}: unknown setting(s): {', '.join(unknown)}")
    return {k: v.strip() for k, v in cp["dsup"].items()}


class Settings:

    def __init__(self, values, sources=None):
        self._v = dict(values)
        self.sources = sources or {}

    def __getattr__(self, name):
        try:
            return self._v[name]
        except KeyError:
            raise AttributeError(name) from None

    def int(self, name):
        return int(self._v[name])

    def float(self, name):
        return float(self._v[name])

    def flag(self, name):
        return self._v[name].strip().lower() in ("1", "true", "yes", "on")

    def words(self, name):
        return self._v[name].split()

    @property
    def target(self):
        """user@host, as ssh wants it."""
        if "@" in self.device:
            return self.device
        return f"{self.user}@{self.device}" if self.user else self.device

    def ssh_extra_args(self):
        args = []
        if self.ssh_options:
            args += shlex.split(self.ssh_options)
        return args

    def secrets(self):
        return [self._v[s.name] for s in SETTINGS if s.secret and self._v[s.name]]

    def redact(self, text):
        for secret in self.secrets():
            text = text.replace(secret, "********")
        return text

    def describe(self):
        lines = []
        for s in SETTINGS:
            v = self._v[s.name]
            if v != s.default:
                shown = "********" if s.secret else v
                lines.append(f"{s.name} = {shown}   [{self.sources.get(s.name, '?')}]")
        return lines


def resolve(cli=None, env=None, ini_path=None):
    """Build Settings.

    cli      {name: value} for options given on the command line (None = not given)
    env      environment mapping (default: os.environ)
    ini_path settings file; if None, DSUP_CONFIG or tests/dsup.ini when it exists
    """
    cli = cli or {}
    env = os.environ if env is None else env
    if ini_path is None:
        ini_path = env.get("DSUP_CONFIG") or None
        if ini_path is None and (TESTS_DIR / "dsup.ini").exists():
            ini_path = str(TESTS_DIR / "dsup.ini")
    ini = read_ini(ini_path) if ini_path else {}

    values, sources = {}, {}
    for s in SETTINGS:
        if cli.get(s.name) not in (None, ""):
            values[s.name], sources[s.name] = str(cli[s.name]), "command line"
        elif env.get(env_name(s.name)):
            values[s.name], sources[s.name] = env[env_name(s.name)], "environment"
        elif ini.get(s.name):
            values[s.name], sources[s.name] = ini[s.name], f"file {ini_path}"
        else:
            values[s.name], sources[s.name] = s.default, "default"
    return Settings(values, sources)
