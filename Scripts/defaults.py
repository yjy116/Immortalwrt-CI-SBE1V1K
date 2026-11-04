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
    generated = replace_exact(generator, [
        ('lan) ipad=${ipaddr:-"192.168.1.1"}', f'lan) ipad=${{ipaddr:-"{LAN_IP}"}}'),
        ("hostname='ImmortalWrt'", f"hostname='{HOSTNAME}'"),
    ])
    themed = replace_exact(luci, [
        ("option mediaurlbase '/luci-static/bootstrap'", f"option mediaurlbase '/luci-static/{THEME}'"),
    ])
    generator.write_text(generated, encoding="utf-8")
    luci.write_text(themed, encoding="utf-8")
