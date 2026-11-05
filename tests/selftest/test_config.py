import pytest

from dsup import config as cfg

pytestmark = [pytest.mark.host, pytest.mark.selftest]


def _ini(tmp_path, text):
    p = tmp_path / "dsup.ini"
    p.write_text("[dsup]\n" + text, encoding="utf-8")
    return str(p)


def test_default_is_used_when_nothing_is_set(tmp_path):
    s = cfg.resolve(cli={}, env={}, ini_path=_ini(tmp_path, ""))
    assert s.user == "root"
    assert s.s1g_device == "wlan0"
    assert s.sources["user"] == "default"


def test_file_beats_default(tmp_path):
    s = cfg.resolve(cli={}, env={}, ini_path=_ini(tmp_path, "device = 10.0.0.5\n"))
    assert s.device == "10.0.0.5"
    assert s.sources["device"].startswith("file")


def test_environment_beats_file(tmp_path):
    s = cfg.resolve(cli={}, env={"DSUP_DEVICE": "10.0.0.6"}, ini_path=_ini(tmp_path, "device = 10.0.0.5\n"))
    assert s.device == "10.0.0.6"
    assert s.sources["device"] == "environment"


def test_command_line_beats_environment(tmp_path):
    s = cfg.resolve(cli={"device": "10.0.0.7"}, env={"DSUP_DEVICE": "10.0.0.6"},
                    ini_path=_ini(tmp_path, "device = 10.0.0.5\n"))
    assert s.device == "10.0.0.7"
    assert s.sources["device"] == "command line"


def test_empty_value_falls_through_to_the_next_source(tmp_path):
    s = cfg.resolve(cli={"device": ""}, env={"DSUP_DEVICE": ""}, ini_path=_ini(tmp_path, "device = 10.0.0.5\n"))
    assert s.device == "10.0.0.5"


def test_unknown_setting_in_the_file_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="bogus"):
        cfg.resolve(cli={}, env={}, ini_path=_ini(tmp_path, "bogus = 1\n"))


def test_target_adds_the_user_unless_the_address_has_one(tmp_path):
    p = _ini(tmp_path, "")
    assert cfg.resolve(cli={"device": "10.0.0.5"}, env={}, ini_path=p).target == "root@10.0.0.5"
    assert cfg.resolve(cli={"device": "bob@10.0.0.5"}, env={}, ini_path=p).target == "bob@10.0.0.5"
    assert cfg.resolve(cli={"device": "10.0.0.5", "user": "admin"}, env={}, ini_path=p).target == "admin@10.0.0.5"


def test_ssh_extra_args_combine_the_options(tmp_path):
    s = cfg.resolve(cli={"ssh_options": "-p 2222 -i '/my keys/id'"},
                    env={}, ini_path=_ini(tmp_path, ""))
    assert s.ssh_extra_args() == ["-p", "2222", "-i", "/my keys/id"]


def test_passwords_are_hidden_in_logs_and_in_the_settings_summary(tmp_path):
    s = cfg.resolve(cli={"s1g_key": "hunter2hunter2", "s1g_ssid": "lab"}, env={}, ini_path=_ini(tmp_path, ""))
    assert "hunter2hunter2" not in s.redact("nmcli ... psk hunter2hunter2 ...")
    assert "********" in s.redact("psk hunter2hunter2")
    assert all("hunter2hunter2" not in ln for ln in s.describe())


def test_every_setting_has_distinct_option_and_environment_names():
    assert len({cfg.option_name(s.name) for s in cfg.SETTINGS}) == len(cfg.SETTINGS)
    assert len({cfg.env_name(s.name) for s in cfg.SETTINGS}) == len(cfg.SETTINGS)


def test_the_example_file_only_uses_known_settings():
    # lines in the example are commented out, uncomment them all and parse
    text = (cfg.TESTS_DIR / "dsup.ini.example").read_text(encoding="utf-8")
    lines = []
    for ln in text.splitlines():
        if ln.startswith("#") and "=" in ln and not ln.startswith("# "):
            ln = ln[1:]
        lines.append(ln)
    import configparser
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_string("\n".join(lines))
    assert set(cp["dsup"]) <= cfg.NAMES


def test_missing_access_point_settings_are_reported(tmp_path):
    from dsup.board import missing_settings
    s = cfg.resolve(cli={"device": "x", "s1g_ssid": "halow"}, env={}, ini_path=_ini(tmp_path, ""))
    assert missing_settings(s) == ["std_ssid", "s1g_key", "std_key"]


def test_all_required_settings_present(tmp_path):
    from dsup.board import missing_settings
    s = cfg.resolve(cli={"device": "x", "s1g_ssid": "a", "s1g_key": "b", "std_ssid": "c", "std_key": "d"},
                    env={}, ini_path=_ini(tmp_path, ""))
    assert missing_settings(s) == []


def test_an_open_network_needs_no_key(tmp_path):
    from dsup.board import missing_settings
    s = cfg.resolve(cli={"device": "x", "s1g_ssid": "a", "s1g_key_mgmt": "none", "std_ssid": "c", "std_key": "d"},
                    env={}, ini_path=_ini(tmp_path, ""))
    assert missing_settings(s) == []
