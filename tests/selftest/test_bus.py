import pytest

from dsup import bus

pytestmark = [pytest.mark.host, pytest.mark.selftest]

CAPTURE = '''\
> Type=signal  Endian=l  Flags=1  Version=1 Cookie=1507  Timestamp="Wed 2026-11-04 03:04:48.608338 UTC"
  Sender=org.freedesktop.DBus  Path=/org/freedesktop/DBus  Interface=org.freedesktop.DBus  Member=NameOwnerChanged
  MESSAGE "sss" {
          STRING "fi.w1.wpa_supplicant1_s1g";
          STRING ":1.1760";
          STRING "";
  };

> Type=signal  Endian=l  Flags=1  Version=1 Cookie=3647  Timestamp="Wed 2026-11-04 03:04:49.156000 UTC"
  Sender=org.freedesktop.DBus  Path=/org/freedesktop/DBus  Interface=org.freedesktop.DBus  Member=NameOwnerChanged
  MESSAGE "sss" {
          STRING "org.example.Other";
          STRING "";
          STRING ":1.9";
  };

> Type=signal  Endian=l  Flags=1  Version=1 Cookie=3648  Timestamp="Wed 2026-11-04 03:04:49.156318 UTC"
  Sender=org.freedesktop.DBus  Path=/org/freedesktop/DBus  Interface=org.freedesktop.DBus  Member=NameOwnerChanged
  MESSAGE "sss" {
          STRING "fi.w1.wpa_supplicant1_s1g";
          STRING "";
          STRING ":1.1847";
  };

> Type=method_call  Endian=l  Flags=0  Version=1 Cookie=1721  Timestamp="Tue 2026-11-03 00:49:03.353658 UTC"
  Sender=:1.1455  Destination=org.freedesktop.DBus  Path=/org/freedesktop/DBus  Interface=org.freedesktop.DBus  Member=StartServiceByName
  UniqueName=:1.1455
  MESSAGE "su" {
          STRING "fi.w1.wpa_supplicant1_s1g";
          UINT32 0;
  };

> Type=method_call  Endian=l  Flags=3  Version=1 Cookie=890275  Timestamp="Wed 2026-11-04 03:02:47.127243 UTC"
  Sender=:1.1770  Destination=:1.1760  Path=/fi/w1/wpa_supplicant1_s1g  Interface=fi.w1.wpa_supplicant1_s1g  Member=RemoveInterface
  UniqueName=:1.1770
  MESSAGE "o" {
          OBJECT_PATH "/fi/w1/wpa_supplicant1_s1g/Interfaces/1";
  };

> Type=method_call  Endian=l  Flags=3  Version=1 Cookie=890276  Timestamp="Wed 2026-11-04 03:02:47.129456 UTC"
  Sender=:1.1770  Destination=:1.1760  Path=/fi/w1/wpa_supplicant1  Interface=fi.w1.wpa_supplicant1  Member=RemoveInterface
  UniqueName=:1.1770
  MESSAGE "o" {
          OBJECT_PATH "/fi/w1/wpa_supplicant1/Interfaces/0";
  };

> Type=error  Endian=l  Flags=1  Version=1 Cookie=198  ReplyCookie=893238  Timestamp="Wed 2026-11-04 03:04:48.612823 UTC"
  Sender=org.freedesktop.DBus  Destination=:1.1770
  ErrorName=org.freedesktop.DBus.Error.NoReply  ErrorMessage="Message recipient disconnected from message bus without replying"
  MESSAGE "s" {
          STRING "Message recipient disconnected from message bus without replying";
  };
'''


def test_parse_epoch_reads_the_busctl_timestamp_as_utc():
    line = '> Type=signal Timestamp="Wed 2026-11-04 03:04:49.156318 UTC"'
    assert bus.parse_epoch(line) == pytest.approx(1793761489.156318)   # 2026-11-04 03:04:49 UTC
    assert bus.parse_epoch("no timestamp here") is None


def test_owner_appeared_ignores_owner_loss_and_other_names():
    # the first event is the name LOSING its owner, the second is another name
    assert bus.owner_appeared(CAPTURE, "fi.w1.wpa_supplicant1_s1g") == pytest.approx(1793761489.156318)
    assert bus.owner_appeared(CAPTURE, "fi.w1.wpa_supplicant1") is None


def test_start_service_calls_give_the_time_and_the_sender():
    calls = bus.start_service_calls(CAPTURE, "fi.w1.wpa_supplicant1_s1g")
    assert len(calls) == 1
    assert calls[0][1] == ":1.1455"
    assert bus.start_service_calls(CAPTURE, "fi.w1.wpa_supplicant1") == []


def test_call_patterns_tell_the_two_supplicants_apart():
    import re
    n_s1g = sum(1 for ln in CAPTURE.splitlines() if re.search(bus.s1g_call("RemoveInterface"), ln))
    n_stock = sum(1 for ln in CAPTURE.splitlines() if re.search(bus.stock_call("RemoveInterface"), ln))
    assert (n_s1g, n_stock) == (1, 1)


def test_errors_keep_their_quoted_message():
    errors = [m for m in bus.messages(CAPTURE) if "ErrorName" in m["fields"]]
    assert errors[0]["fields"]["ErrorName"] == "org.freedesktop.DBus.Error.NoReply"
    assert errors[0]["fields"]["ErrorMessage"].startswith('"Message recipient')
