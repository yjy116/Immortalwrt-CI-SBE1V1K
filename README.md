# ImmortalWrt CI · SBE1V1K

为 Askey / Spectrum **SBE1V1K（RTQ7300T）** 编译 ImmortalWrt 固件的 GitHub Actions 仓库。参考 [Immortalwrt-CI-CR1000A-OWRT](https://github.com/yjy116/Immortalwrt-CI-CR1000A-OWRT) 的组织方式，采用 SBE1V1K 原生 `qualcommbe/ipq95xx` 设备支持。

## 默认设置

| 项目 | 配置 |
| --- | --- |
| 管理地址 | `192.168.70.1` |
| 主机名 | `SBE1V1K` |
| 管理用户 | `root`，无预设密码；首次登录后设置 |
| 无线 | 保持上游初始禁用；启用前设置实际国家/地区与加密口令 |
| 主题 | Vantage |
| 源码 | ImmortalWrt `master`，默认锁定提交 `89f1ef18c888f841633f19f92655ee4b7f7716a4` |

源码地址和默认提交记录在 [Config/source.json](Config/source.json)。默认配置包括 HomeProxy、PassWall、OpenClash、Nikki、AdGuard Home、DDNS-Go、Lucky、Tailscale、EasyTier、SQM、UPnP、ttyd、Samba4、WireGuard 和 ZeroTier。软件包优先采用官方 feeds，外部补充仅涉及 Vantage、Nikki、EasyTier 和 Lucky。Aurora、DAE / Honk 未移植。

## 开始编译

1. 打开本仓库的 [Actions](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions)，选择 `SBE1V1K.yml` 对应的编译工作流。
2. 点击 **Run workflow**，按下表选择参数。
3. 完成后从该次运行的 **Artifacts** 下载结果；完整固件构建启用 `PUBLISH` 时也会发布到 [Releases](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/releases)。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `WIFI_MODE` | `both` | `both` 同时构建带无线与无无线版本；`yes` 仅带无线；`no` 仅无无线 |
| `CONFIG_ONLY` | `false` | 为 `true` 时只解析并验证配置、保存配置与来源记录，不编译固件或发布 Release |
| `PUBLISH` | `true` | 完整固件构建成功后发布 Release |
| `SOURCE_REF` | 留空 | 使用 `Config/source.json` 锁定提交；可填 `master` 或其他包含 SBE1V1K 的分支/提交 |

带无线版本包含 ath12k 驱动、QCN9274 固件和 SBE1V1K 板级数据，但无线初始仍为禁用状态。无无线版本用于有线路由用途。构建保存实际源码提交，便于定位结果；选择滚动分支时，不同时间运行可能得到不同源码。

无无线版本移除 ath12k 驱动及对应固件，不修改设备树或回收无线保留内存。`192.168.70.1` 是新安装或恢复默认后的地址；保留旧配置升级时，已有 LAN 地址通常继续生效。

`CHECK.yml` 在 push / pull request 时执行仓库静态验证。配置检查、完整固件编译和实机测试是不同验证阶段；不能互相替代。

2026-11-04 验证：代码提交 `1b2ca18` 的 [26 项 Linux 测试与工作流检查](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions/runs/41750028265)及 [WiFi / 无 WiFi 双配置展开](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions/runs/41750030966)均通过。完整固件是否成功请以相应 Actions / Release 为准；尚无实机验证记录。

## 下载文件

保留上游文件名，以及 `sha256sums`、`*.buildinfo`、`profiles.json` 等构建记录。Release 标签格式为 `sbe1v1k-wifi-<mode>-<runid>-<attempt>`，其中 `<mode>` 是该版本的 `yes` 或 `no`。

| 文件后缀 | 用途 |
| --- | --- |
| `-initramfs-uImage.itb` | RAM 启动、首次安装流程与恢复所需镜像 |
| `-squashfs-sysupgrade.bin` | 已按适用流程安装 OpenWrt / ImmortalWrt 后的系统升级 |
| `-squashfs-factory.bin` | 上游生成的 rootfs 镜像，不能按名称推断为原厂 Web 可直接刷入的固件 |

**首次安装涉及设备专用的串口、eMMC 与启动环境操作。** 请先阅读 [设备说明](docs/DEVICE.md) 和其中的官方来源；本仓库不提供一键刷机脚本。编译成功仅证明构建完成，不代表实机启动、网络、无线或升级验证通过。

## 修改配置

在 `Config/` 中调整编译选项，在 `Scripts/defaults.py` 中设置默认 IP、主机名和主题。LAN 地址和主机名只修改上游生成默认值，保留配置升级时不会由本仓库脚本重置。Vantage 首次注册沿用其上游行为，可能切换已有主题。修改后先运行静态检查和 `CONFIG_ONLY=true` 的配置检查，再执行完整构建；从日志确认所需软件包没有被依赖解析取消。

本地检查：`python3 -m unittest discover -s Tests -v`。Linux CI 对测试设置 60 秒超时，并运行 shell 语法检查与 actionlint。每个显式配置选项均会在 `make defconfig` 后核对，缺包会使任务失败。

主源码与外部插件配方固定提交；官方 feeds 仍按源码提供的分支更新，实际 SHA 会记录到产物中。EasyTier 与 Lucky 沿用其上游二进制下载配方，其中并非所有下载都有固定内容哈希；这里不宣称完全可复现构建。

只安装选中插件及其递归依赖，外部包的官方 feed / host 依赖列在 `Config/packages.json` 的 `feed_dependencies` 中。不安装无关的软件包集合；Kconfig 输出错误时，即使命令返回零也会使配置验证失败。

请保留 SBE1V1K 的原生设备树、校准数据处理、网口定义和 eMMC 升级逻辑。参考仓库中针对 CR1000A 的设备修补不能直接用于本机型。

## 来源

- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)
- [OpenWrt SBE1V1K 设备页](https://openwrt.org/toh/askey/sbe1v1k)
- [CR1000A 参考编译仓库](https://github.com/yjy116/Immortalwrt-CI-CR1000A-OWRT)
- [设备适配依据、安装与支持限制](docs/DEVICE.md)
