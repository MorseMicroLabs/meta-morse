import shlex

import pytest

from dsup.supplicant import S1G_SVC, STOCK_SVC

pytestmark = [pytest.mark.halow]


def test_s02_unit_and_policy(board, checks):
    def has(path, pattern):
        return board.ok(f"grep -q -- {shlex.quote(pattern)} {shlex.quote(path)}")

    checks.eq("wpa_supplicant_s1g.service is enabled at boot", "enabled",
              board.sh("systemctl is-enabled wpa_supplicant_s1g"))
    u = "/usr/lib/systemd/system"
    checks.ok("s1g unit: BusName is the s1g name", has(f"{u}/wpa_supplicant_s1g.service", f"^BusName={S1G_SVC}$"))
    checks.ok("s1g unit: starts wpa_supplicant_s1g -u",
              has(f"{u}/wpa_supplicant_s1g.service", "^ExecStart=/usr/sbin/wpa_supplicant_s1g -u"))
    checks.ok("stock unit still uses the stock name", has(f"{u}/wpa_supplicant.service", f"^BusName={STOCK_SVC}$"))
    checks.ok("stock unit still starts wpa_supplicant",
              has(f"{u}/wpa_supplicant.service", "^ExecStart=/usr/sbin/wpa_supplicant -u"))

    a = f"/usr/share/dbus-1/system-services/{S1G_SVC}.service"
    checks.ok("activation file names the s1g service", has(a, f"^Name={S1G_SVC}$"))
    checks.ok("activation file starts the s1g binary", has(a, "^Exec=/usr/sbin/wpa_supplicant_s1g -u"))
    checks.ok("activation file hands over to systemd", has(a, "^SystemdService=wpa_supplicant_s1g.service"))

    p = "/etc/dbus-1/system.d/dbus-wpa_supplicant_s1g.conf"
    checks.ok("policy lets root own the s1g name", has(p, f'allow own="{S1G_SVC}"'))
    checks.ok("policy denies everybody else", has(p, f'deny own="{S1G_SVC}"'))
    checks.ok("policy does not touch the stock name", not has(p, f'own="{STOCK_SVC}"'))

    checks.info(f"  informational: Restart={board.sh('systemctl show -p Restart --value wpa_supplicant_s1g')} on "
                "wpa_supplicant_s1g.service (a crash is only recovered by D-Bus activation unless it is 'always')")
