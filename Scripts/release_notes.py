"""Render visible firmware links and build information for a release."""
from pathlib import Path
from urllib.parse import quote

BYTES_PER_MIB = 1024 * 1024


def download_url(args, filename):
    return f"https://github.com/{args.repository}/releases/download/{quote(args.tag, safe='')}/{quote(filename, safe='')}"


def firmware_links(args, plan):
    labels = (("sysupgrade", "系统升级固件"), ("factory", "Factory 镜像"),
              ("initramfs", "Initramfs 恢复镜像"))
    links = []
    for marker, label in labels:
        image = next(item for item in plan["firmware"] if marker in item["original"])
        links.append(f"- [{label}（{image['size'] / BYTES_PER_MIB:.1f} MiB）]({download_url(args, image['name'])})")
    return "\n".join(links)


def package_info(directory):
    manifest = next(Path(directory).glob("*.manifest"))
    entries = dict(line.split(" - ", 1) for line in manifest.read_text().splitlines())
    plugins = sorted(name for name in entries if name.startswith(("luci-app-", "luci-theme-")))
    return entries["kernel"].split("~", 1)[0], " ".join(plugins)


def render_notes(args, plan):
    kernel, plugins = package_info(args.artifacts)
    source = plan["source"]
    version = "WiFi 版" if plan["wifi"] == "yes" else "无 WiFi 版"
    wireless = ("WiFi 名称：SBE1V1K；初始禁用，启用前设置实际国家和加密口令。"
                if plan["wifi"] == "yes" else "无线功能：此版本不含 WiFi 驱动和固件。")
    fan = ("\n风扇控制：系统 → 风扇控制；支持四档温度阈值，默认原生自动温控。"
           if "luci-app-sbe1v1k-fan" in plugins.split() else "")
    config = next(item for item in plan["assets"] if item["original"] == "config.txt")
    return f"""## 固件下载 · {version}

{firmware_links(args, plan)}

[SHA256 校验表]({download_url(args, plan['checksum_file'])}) · [编译配置]({download_url(args, config['name'])})

源码：{source['repository']}
分支：{source['branch']}
提交：{source['commit']}

配置：SBE1V1K-WIFI-{plan['wifi'].upper()}（{version}）
平台：qualcommbe / ipq95xx
构建时间：{plan['build_time']}（北京时间，原构建任务创建时间）
内核版本：{kernel}

登录地址：192.168.70.1
登录密码：无；首次登录请设置 root 密码。
{wireless}{fan}

插件列表：{plugins}

构建记录归档保留原始配置、来源、校验值和 profiles.json；release-files.json 提供原文件名到本页文件名的对应关系。固件只重命名，内容不变。
CI 提交：{plan['ci_commit']}
原构建：https://github.com/{args.repository}/actions/runs/{plan['run_id']}

factory.bin 不是原厂 Web 直刷包；首次安装请阅读 [设备说明](https://github.com/{args.repository}/blob/main/docs/DEVICE.md)。
本发布证明编译和产物校验通过，不代表实机验证。
"""
