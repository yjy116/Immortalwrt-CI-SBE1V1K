"""Change only pristine defaults; sysupgrade keeps the user's saved UCI config."""

from pathlib import Path

LAN_IP = "192.168.70.1"
HOSTNAME = "SBE1V1K"
THEME = "vantage"


def replace_exact(path, replacements):
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError(f"Expected one upstream default {old!r} in {path}")
        text = text.replace(old, new)
    return text


def apply_defaults(source):
    source = Path(source)
    generator = source / "package/base-files/files/bin/config_generate"
    luci = source / "feeds/luci/modules/luci-base/root/etc/config/luci"
    wireless = source / "package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc"
    generated = replace_exact(generator, [
        ('lan) ipad=${ipaddr:-"192.168.1.1"}', f'lan) ipad=${{ipaddr:-"{LAN_IP}"}}'),
        ("hostname='OWRT'", f"hostname='{HOSTNAME}'"),
    ])
    themed = replace_exact(luci, [
        ("option mediaurlbase '/luci-static/bootstrap'", f"option mediaurlbase '/luci-static/{THEME}'"),
    ])
    radio_defaults = replace_exact(wireless, [
        ("set ${s}.country='${country || 'CN'}'", "set ${s}.country='${country || ''}'"),
        ("set ${si}.ssid='${defaults?.ssid || 'OWRT'}'", "set ${si}.ssid='${defaults?.ssid || 'SBE1V1K'}'"),
        ("set ${si}.encryption='${defaults?.encryption || 'psk2+ccmp'}'",
         "set ${si}.encryption='${defaults?.encryption || encryption}'"),
        ("set ${si}.key='${defaults?.key || '12345678'}'", "set ${si}.key='${defaults?.key || ''}'"),
        ("set ${si}.disabled='0'", "set ${si}.disabled='1'"),
    ])
    generator.write_text(generated, encoding="utf-8")
    luci.write_text(themed, encoding="utf-8")
    wireless.write_text(radio_defaults, encoding="utf-8")
