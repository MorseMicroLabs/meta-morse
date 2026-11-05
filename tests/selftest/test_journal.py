import re

import pytest

from dsup import journal

pytestmark = [pytest.mark.host, pytest.mark.selftest]

LOG = """\
Nov 04 03:30:15 imx6ul-var-dart NetworkManager[10145]: <info>  [1793763015.2858] device (wlan0): state change: activated -> unmanaged (reason 'removed', sys-iface-state: 'removed')
Nov 04 03:30:16 imx6ul-var-dart wpa_supplicant_s1g[10390]: wlan0: CTRL-EVENT-DISCONNECTED bssid=94:bb:43:dc:f9:84 reason=3 locally_generated=1
Nov 04 03:30:20 imx6ul-var-dart NetworkManager[10145]: <info>  [1793763020.1000] device (wlan0): state change: ip-config -> activated (reason 'none', sys-iface-state: 'managed')
Nov 04 03:30:21 imx6ul-var-dart NetworkManager[10145]: <info>  [1793763021.5000] device (wlan1): state change: ip-config -> activated (reason 'none', sys-iface-state: 'managed')
Nov 04 03:30:30 imx6ul-var-dart NetworkManager[10145]: <info>  [1793763030.2500] device (wlan0): state change: ip-config -> activated (reason 'none', sys-iface-state: 'managed')
"""


def test_nm_epoch_reads_networkmanagers_own_timestamp():
    assert journal.nm_epoch(LOG.splitlines()[0]) == pytest.approx(1793763015.2858)
    assert journal.nm_epoch(LOG.splitlines()[1]) is None        # a supplicant line has none


def test_activation_epochs_only_for_the_asked_interface_and_only_activated():
    assert journal.activation_epochs(LOG, "wlan0") == [1793763020.1, 1793763030.25]
    assert journal.activation_epochs(LOG, "wlan1") == [1793763021.5]


def test_log_after_epoch_drops_older_networkmanager_lines_but_keeps_stamp_less_lines():
    out = journal.log_after_epoch(LOG, 1793763020.0)
    assert "activated -> unmanaged" not in out                  # NM line before the cut
    assert "CTRL-EVENT-DISCONNECTED" in out                     # no stamp: kept
    assert out.count("-> activated") == 3


def test_crash_filter_flags_a_networkmanager_dump_but_not_a_deliberate_supplicant_kill():
    pat = re.compile(journal.CRASH_FILTER)
    assert pat.search("systemd[1]: NetworkManager.service: Main process exited, code=dumped, status=11/SEGV")
    assert pat.search("systemd[1]: NetworkManager.service: Failed with result 'core-dump'.")
    assert pat.search("kernel: NetworkManager[123]: segfault at 0 ip 0000 sp 0000 error 4 in NetworkManager")
    assert pat.search("systemd[1]: wpa_supplicant_s1g.service: Main process exited, code=dumped, status=11/SEGV")
    assert not pat.search("systemd[1]: wpa_supplicant_s1g.service: Main process exited, code=killed, status=9/KILL")
    assert not pat.search("systemd[1]: wpa_supplicant_s1g.service: Main process exited, code=exited, status=0/SUCCESS")


def test_glib_pattern_matches_assertions_and_criticals():
    pat = re.compile(journal.GLIB_PATTERN)
    assert pat.search("NetworkManager[10145]: g_variant_builder_add: assertion 'x' failed")
    assert pat.search("NetworkManager[10145]: ** (NetworkManager:10145): CRITICAL **: foo")
    assert not pat.search("NetworkManager[10145]: <info>  [1.0] manager: startup complete")
