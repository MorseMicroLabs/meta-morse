# Dual-supplicant tests

These tests validate that NetworkManager functions with two supplicants on the
same host, without interfering or crashing.

## What the tests check

The board has two radios, and each radio has its own supplicant:

| Radio | Network interface | Supplicant | D-Bus name |
|-------|-------------------|------------|------------|
| Morse Micro Wi-Fi HaLow | `wlan0` | `wpa_supplicant_s1g` | `fi.w1.wpa_supplicant1_s1g` |
| Standard Wi-Fi | `wlan1` | `wpa_supplicant` | `fi.w1.wpa_supplicant1` |

The tests check that:

- On boot and for every test, NetworkManager never crashes or restarts;
- Stopping one supplicant does not impact the other radio;
- The supplicants start cleanly;
- NetworkManager can manage the interfaces independently;
- Both radios can establish and maintain connectivity;
- Validates the patches apply cleanly to NetworkManager 1.46.0 and 1.46.6.

The full list of tests is at the end of this file.

## Requirements

- Python 3.10 or newer;
- `ssh`;
- Network access to the DUT over an interface you're not under test - eg Ethernet;
- non-interactive root login via ssh. Setup keys or remove the password for test purposes;
- `NetworkManager`, `wpa_supplicant` and `wpa_supplicant_s1g` must be installed on the DUT
- A access point for both radio.

Some tests need more, and they skip with a clear message if it is missing:

- `t23` needs WPA3 access points.
- `t24` downloads NetworkManager source tarballs, so it needs internet access (or the tarballs
  already on disk).

## Set up

Run all commands in this `tests` folder.

### Create the python environment

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Verify DUT ssh access

```sh
ssh root@<board address> true
```

It must print nothing and return at once. If it asks for a password, set up an ssh key first.

### Configure the tests

```sh
cp dsup.ini.example dsup.ini
```

Then edit `dsup.ini`. These settings are *required*: the DUT address, and for each radio the SSID
and its password:

```ini
[dsup]
device = 192.168.1.113
s1g_ssid = MyHaLowNetwork
s1g_key = my-halow-password
std_ssid = MyWiFiNetwork
std_key = my-wifi-password
```

Before the tests start they delete every Wi-Fi connection on the board and create two new ones
for the access points you gave. Connections you had set up before are not expected to survive a run. 

Everything else is optional. The most useful settings are:

| Setting | What it is | Default |
|---------|------------|---------|
| `device` | Address of the board.  | |
| `user` | Login name on the board. | `root` |
| `ssh_options` | Any other ssh options, written as on the ssh command line. Example: `-p 2222 -i ~/.ssh/board_key`. | none |
| `ssh_connect_timeout` | Seconds to wait when connecting. Make it larger on a slow link. | `30` |
| `s1g_ssid`, `s1g_key` | The access point for the HaLow radio, and its password. | required |
| `std_ssid`, `std_key` | The access point for the standard radio, and its password. | required |
| `s1g_key_mgmt`, `std_key_mgmt` | Security of those connections: `sae` (WPA3) or `wpa-psk` (WPA2). | `sae` |
| `s1g_pmf`, `std_pmf` | PMF setting: `3` required, `2` optional, `1` disable, `0` default. | `3` |
| `recovery_limit` | Seconds allowed for wlan0 to come back after the HaLow supplicant returns. | `15` |
| `build_dir` | Your Yocto build directory (for the build tests). | none |

If you leave the access point name empty, the tests use whatever connection each radio already has.

### Run framework selftests

```sh
pytest selftest
```

This runs the tests of the test framework itself. They must all pass.

### Running the tests

| You want to | Command |
|-------------|---------|
| Run all tests | `pytest` |
| Run one test | `pytest -k t01` |
| Run several tests | `pytest -k "t01 or t02 or s03"` |
| Run only the HaLow tests | `pytest -m halow` |
| Run only the standard-radio tests | `pytest -m standard` |
| Run only the tests that do not need the board | `pytest -m host` |
| List the tests without running them | `pytest --collect-only -q` |
| Run the test that reboots the board too | `pytest --run-disruptive` |
| Run only the reboot test | `pytest --run-disruptive -k t22` |
| Stop at the first failing test | `pytest -x` |
| Run again only the tests that failed last time | `pytest --lf` |
| See each test's name while running | `pytest -v` |
| Use another settings file | `pytest --dsup-config /path/to/my.ini` |
| Allow tests more time (slow link) | `pytest --timeout 1800` |

A full run takes about 20 minutes.
Do not run two test runs at the same time against the same board.

## Troubleshooting

| Problem | Reason |
|---------|--------|
|`t17`, `t24` or `u01` skip | They need your Yocto build. Set `build_dir` |
|`t23` fails on the key-mgmt or PMF checks | `t23` expects WPA3 with required PMF on both radios. If your access points use something else, set `s1g_key_mgmt`, `std_key_mgmt`, `s1g_pmf`, `std_pmf` |
| I stopped the run with Ctrl-C | The tests put the board back to normal when they stop. If the process was killed hard, see the safety section for what to check. |

## Safety

The tests are made to run on a DUT. They interact with the radios. You can expect:

- Services are stopped, restarted and killed;
- Radios are released and handed back;
- `/proc/sys/kernel/core_pattern` is configured to write files in `core_dir`;
- NetworkManager's log level is raised to TRACE;
- systemd configuration is manipulated;
- All existing Wi-Fi connections on the board are deleted (see "Configure the tests");
- Some tests are "disruptive" and reboot the board;

Apart from the Wi-Fi connections, the tests restore everything they change when they finish.
The deleted Wi-Fi connections are not restored.

If a run was forcefully stopped, you can restore it with:

```sh
systemctl unmask --runtime wpa_supplicant_s1g
rm -rf /run/systemd/system/wpa_supplicant_s1g.service.d; systemctl daemon-reload
rm -f /etc/NetworkManager/conf.d/99-t22-trace.conf
nmcli connection delete dsup-halow; nmcli connection delete dsup-standard
echo '|/bin/false' > /proc/sys/kernel/core_pattern    # or the value you had before
nmcli general logging level INFO domains ALL
systemctl restart NetworkManager wpa_supplicant wpa_supplicant_s1g
```

## Test Summary

`s` tests look at how the two supplicants are set up. `t` tests disturb the system and watch what
happens. `u` tests are NetworkManager's own unit tests.

| Test | What it does | A pass means |
|------|--------------|--------------|
| `s01` bus identity | Reads the D-Bus names and what each supplicant exports. | Each supplicant has its own name, and no object uses the other one's names. |
| `s02` unit and policy | Reads the systemd unit, the D-Bus activation file and the D-Bus policy of `wpa_supplicant_s1g`. | They name the HaLow supplicant, and the standard one is unchanged. |
| `s03` D-Bus activation | Stops NetworkManager and the HaLow supplicant, waits 20 s, then makes one D-Bus call to the HaLow name. | Only that call starts the supplicant. |
| `s04` error names | Makes calls that must fail, and reads the error names. | The HaLow supplicant sends the error names NetworkManager looks for. |
| `s05` signals | Creates and removes a HaLow interface by hand. | The signals are sent under the HaLow names, and none under the standard names. |
| `s06` NM reactivates | Stops the HaLow supplicant with NetworkManager running. | NetworkManager starts it again. |
| `t01` create first try | Releases wlan0 and lets NetworkManager create it again. | One create request and connect. |
| `t02` release | Releases wlan0, then hands it back. | One remove request to the HaLow supplicant. |
| `t03` five cycles | Repeats release and create five times. | No stale interface created. |
| `t04` stop s1g | Stops the HaLow supplicant for 20 s. | NetworkManager does not crash and wlan1 does not notice. |
| `t05` create with s1g absent | Asks NetworkManager to create wlan0 while the supplicant is down. | NetworkManager does not crash and wlan0 connects. |
| `t06` restart isolated | Restarts one supplicant and watches the other radio. | The other radio keeps its connection and its interfaces. |
| `t08` NM restart, s1g down | Restarts NetworkManager while the HaLow supplicant is down. | wlan1 comes up. wlan0 follows when the supplicant is back. |
| `t09` NM restart | Restarts NetworkManager. | Both radios come back. |
| `t10` connection cycles | Takes a radio's connection down and up three times, with traffic. | The gateway answers each time. Runs for each radio. |
| `t12` both radios busy | Sends traffic on both radios for 30 s. | No packets are lost. |
| `t13` scan | Scans on both radios. | Both supplicants and NetworkManager list access points. |
| `t14` WFD IEs | Releases and hands back wlan1. | No GLib assertion and no crash while the P2P device is released. |
| `t15` cancel race | Starts and cancels a wlan0 connection 20 times, fast. | NetworkManager survives. |
| `t16` interface removed | Removes an interface from under NetworkManager, for each radio. | NetworkManager notices and the radio recovers. |
| `t17` build warnings | Reads the compile log. | No compiler warnings in the supplicant code. |
| `t18` full sequence | A complete sequence. | The first attempt works and stopping the HaLow supplicant does not crash NetworkManager. |
| `t19` recovery | With `Restart=always`: restart, `kill -9` and `kill -TERM` the HaLow supplicant. | wlan0 is connected within 15 s of the supplicant coming back, and NetworkManager is untouched. |
| `t20` NetworkManager first | Starts NetworkManager before the HaLow supplicant. | wlan0 comes up on the first attempt. |
| `t21` supplicant first | Starts the HaLow supplicant before NetworkManager. | wlan0 comes up on the first attempt. |
| `t22` reboot | Reboots the board (`--run-disruptive`). | Both radios come up, wlan0 on the first attempt, no crash. |
| `t23` SAE and PMF | Checks both connections and the stock capabilities across a HaLow restart. | WPA3 with required PMF, and nothing changed for the standard radio. |
| `t24` patches apply | Applies the patches to NetworkManager 1.46.0 and 1.46.6. | No failed hunks and no fuzz. |
| `u01` unit tests | Runs NetworkManager's own WiFi unit tests on the board. | They pass. |

`pytest selftest` runs a further set of fast tests of the framework itself. They need no board.
