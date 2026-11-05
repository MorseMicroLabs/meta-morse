"""How the state monitor reads its samples."""
import pytest

from dsup.monitors import PingMonitor, StateMonitor

pytestmark = [pytest.mark.host, pytest.mark.selftest]


def _mon(text):
    m = StateMonitor(None, "x", "wlan0")
    m.text = text
    return m


def test_all_connected_and_up():
    m = _mon("1.0 connected up\n2.0 connected up\n")
    assert (m.not_connected, m.unreachable) == (0, 0)


def test_a_busy_networkmanager_is_not_a_lost_connection():
    m = _mon("1.0 connected up\n2.0 nm-unreachable up\n3.0 nm-unreachable up\n4.0 connected up\n")
    assert m.not_connected == 0
    assert m.unreachable == 2


def test_networkmanager_reporting_another_state_counts():
    m = _mon("1.0 connected up\n2.0 connecting (configuring) up\n")
    assert m.not_connected == 1


def test_a_link_that_is_down_counts_even_when_networkmanager_is_silent():
    m = _mon("1.0 nm-unreachable down\n2.0 connected dormant\n")
    assert m.not_connected == 2
    assert m.unreachable == 1


def _ping(text):
    m = PingMonitor(None, "x", "wlan1", "gw")
    m.text = text
    return m


def test_isolated_lost_probes_are_not_a_run():
    m = _ping("1 ok\n2 lost\n3 ok\n4 lost\n5 ok\n6 lost\n7 ok\n")
    assert (m.lost, m.longest_lost_run) == (3, 1)


def test_consecutive_lost_probes_are_counted():
    m = _ping("1 ok\n2 lost\n3 lost\n4 lost\n5 ok\n6 lost\n")
    assert (m.lost, m.longest_lost_run) == (4, 3)


def test_no_probes_lost():
    assert _ping("1 ok\n2 ok\n").longest_lost_run == 0
