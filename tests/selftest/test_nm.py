"""Connection set-up for the access points given in the settings (a fake board records the commands)."""
import pytest

from dsup import config as cfg
from dsup import nm
from dsup.board import Board, Result

pytestmark = [pytest.mark.host, pytest.mark.selftest]


class FakeBoard:
    def __init__(self, active="old-connection", refuse=None):
        self.commands = []
        self.active = active
        self.refuse = refuse      # None, "error" (nmcli fails) or "fallback" (stays on the old connection)

    def run(self, cmd, timeout=0, **kw):
        self.commands.append(cmd)
        if "connection up dsup-" in cmd and not self.refuse:
            self.active = cmd.split("connection up ")[1].split()[0]
        if "connection up dsup-" in cmd and self.refuse == "error":
            return Result(4, "", "Error: Connection activation failed: Secrets were required")
        return Result(0, "", "")

    def sh(self, cmd, timeout=0):
        self.commands.append(cmd)
        return self.active if "GENERAL.CONNECTION" in cmd else ""


def _radio(**kw):
    s = cfg.resolve(cli=kw, env={}, ini_path="/dev/null")
    return nm.make_radios(s)


def test_provision_creates_a_connection_with_the_ssid_key_security_and_pmf():
    halow, _ = _radio(s1g_ssid="HaLowNet", s1g_key="pw-halow-1234", s1g_key_mgmt="sae", s1g_pmf="3")
    b = FakeBoard()
    nm.provision(b, halow)
    add = next(c for c in b.commands if c.startswith("nmcli connection add"))
    for part in ("ifname wlan0", "con-name dsup-halow", "ssid HaLowNet", "wifi-sec.key-mgmt sae",
                 "wifi-sec.psk pw-halow-1234", "wifi-sec.pmf 3"):
        assert part in add
    assert halow.conn == "dsup-halow" and halow.provisioned


def test_provision_fails_with_a_clear_message_when_the_connection_cannot_be_made():
    halow, _ = _radio(s1g_ssid="HaLowNet", s1g_key="wrong")
    with pytest.raises(RuntimeError, match="could not connect to 'HaLowNet'.*Secrets were required"):
        nm.provision(FakeBoard(refuse="error"), halow)


def test_provision_fails_when_networkmanager_fell_back_to_another_connection():
    halow, _ = _radio(s1g_ssid="HaLowNet", s1g_key="wrong")
    with pytest.raises(RuntimeError, match="connected through 'old-connection'"):
        nm.provision(FakeBoard(refuse="fallback"), halow)


def test_open_network_gets_no_security_properties():
    _, std = _radio(std_ssid="Open", std_key_mgmt="none")
    b = FakeBoard()
    nm.provision(b, std)
    add = next(c for c in b.commands if c.startswith("nmcli connection add"))
    assert "wifi-sec" not in add


def test_deprovision_removes_the_connection_of_a_failed_set_up():
    halow, _ = _radio(s1g_ssid="HaLowNet", s1g_key="pw-halow-1234")
    b = FakeBoard()
    nm.provision(b, halow)
    b.commands.clear()
    nm.deprovision(b, halow)
    assert any("connection delete dsup-halow" in c for c in b.commands)
    assert not any("connection up" in c for c in b.commands)
    assert not halow.provisioned


def test_only_wifi_connections_are_deleted():
    class Listing(FakeBoard):
        def sh(self, cmd, timeout=0):
            self.commands.append(cmd)
            return ("aaa:802-11-wireless\nbbb:802-3-ethernet\nccc:802-11-wireless\n"
                    "ddd:loopback\n")
    b = Listing()
    nm.delete_wifi_connections(b)
    deleted = [c for c in b.commands if "connection delete" in c]
    assert deleted == ["nmcli connection delete uuid aaa", "nmcli connection delete uuid ccc"]


def test_deprovision_does_nothing_for_a_radio_that_was_not_provisioned():
    halow, _ = _radio()
    b = FakeBoard()
    nm.deprovision(b, halow)
    assert b.commands == []


def test_the_password_does_not_reach_the_command_trace():
    s = cfg.resolve(cli={"device": "x", "s1g_key": "pw-halow-1234"}, env={}, ini_path="/dev/null")
    board = Board(s)
    board._record("$ nmcli connection add ... wifi-sec.psk pw-halow-1234")
    assert "pw-halow-1234" not in "\n".join(board.trace)
    assert "********" in board.trace[-1]
