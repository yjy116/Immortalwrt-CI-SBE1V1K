# SBE1V1K 设备与构建说明

核验日期：2026-11-04。设备别名为 Askey SBE1V1K、Spectrum SBE1V1K、Askey RTQ7300T。

## 源码依据

本仓库直接跟随 **[yjy116/immortalwrt](https://github.com/yjy116/immortalwrt) 的 `owrt` 分支最新提交**，其来源为 [VIKINGYFY/immortalwrt](https://github.com/VIKINGYFY/immortalwrt/tree/owrt)，不固定主源码提交。本文硬件核验样本为 [`a8d4a44c8ede4c703e8866fbf709b34dd1506294`](https://github.com/yjy116/immortalwrt/commit/a8d4a44c8ede4c703e8866fbf709b34dd1506294)，与当时 VIKINGYFY 的 `owrt` 一致；下方固定链接用于保留核验依据，不控制后续构建版本。实际源码 SHA 以每次运行产物为准。

VIKINGYFY 的 `owrt` 与 `main` 均包含 SBE1V1K，但无线固件、target 默认包、设备树和 PPE 实现有差异。**`main` 不能作为 `owrt` 的同义替换。** 本仓库的配置和验证以 `owrt` 为依据；分支更新后若设备或软件包接口改变，构建检查会明确报告不兼容项。

| 编译项 | 值 |
| --- | --- |
| Target / Subtarget | `qualcommbe/ipq95xx` |
| Device profile | `askey_sbe1v1k` |
| 软件包架构 | `aarch64_cortex-a53` |
| 核验样本的内核系列 | Linux 6.18 |
| Device tree | `ipq9570-sbe1v1k.dts`，包含 `ipq9574-common.dtsi` 与 `ipq9574-common-wifi-pci.dtsi` |

对应配置符号为 `CONFIG_TARGET_qualcommbe`、`CONFIG_TARGET_qualcommbe_ipq95xx` 和 `CONFIG_TARGET_qualcommbe_ipq95xx_DEVICE_askey_sbe1v1k`。

来源：[owrt 设备镜像定义](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/image/ipq95xx.mk)、[owrt target 定义](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/Makefile)、[核验时的 main 设备定义](https://github.com/VIKINGYFY/immortalwrt/blob/f9b0ce7650fdcc7f4793256a3ae43c1132e2bc49/target/linux/qualcommbe/image/ipq95xx.mk)。

## 硬件与原生配置

| 项目 | 设备定义 |
| --- | --- |
| SoC | Qualcomm IPQ9570 |
| 内存 / 存储 | 2 GB RAM / 8 GB eMMC |
| WAN | `wan`：10GbE，RTL8261BE |
| LAN | `lan1`：2.5GbE，QCA8081；`lan2`、`lan3`：1GbE，QCA8075 |
| 无线 | 2.4 / 5 / 6 GHz，ath12k / QCN9274 固件与 WSI 多射频支持 |
| 散热 | PWM 风扇与设备树温控策略 |
| USB | 无外露 USB 接口 |

[OpenWrt 首次支持提交](https://github.com/openwrt/openwrt/commit/31c49dd07660a8c9a3b8a34f6fb66ec37244c948)明确列出 USB ports 为 none。[Askey RTQ7300T 官方规格](https://www.askey.com/products-detail/349/)和 [Spectrum WiFi 7 手册](https://d15yx0mnc9teae.cloudfront.net/sites/default/files/2024-10/WiFi%207%20User%20Guide%20v13.pdf)列出的接口为以太网、电源和复位。未据此推断板上不存在测试焊盘；本仓库按可用外部接口去除 USB 外设包，并在最终固件 manifest 中检查没有残留 USB 驱动或打印服务。

原生 LAN bridge 包含 `lan1 lan2 lan3`。设备树负责网口、MAC、PCIe、风扇等硬件描述；板级校准脚本从本机 `0:ART` 读取射频校准数据。构建仓库保留这些实现，不替换设备校准数据，不采用 CR1000A 的 ath11k、Q6、NAND 或网口修补。

带无线版本采用 `owrt` 选择的 **`ath12k-firmware-qcn9274-ddwrt`**、`ipq-wifi-askey_sbe1v1k` 和 `kmod-ath12k`。该固件包与官方 `ath12k-firmware-qcn9274` 不是同一个配置选项，不能同时照搬。设备依赖还包括 `kmod-hwmon-pwmfan`、`kmod-phy-realtek` 和 `rtl826x-firmware`；target 默认包含 `kmod-qcom-ppe`、`kmod-fs-f2fs` 和 `f2fs-tools`，后者依赖 `mkf2fs`、`f2fsck`。无无线版本移除无线包，保留有线网络、eMMC 和风扇依赖。

`owrt` 为 qualcommbe 的 ath12k 编译启用 `ATH12K_PPE_DS_SUPPORT`，采用该分支的原生 PPE 路径。`kmod-nss-wifi-drv` 的目标限制为 qualcommax 的 IPQ807x / IPQ60xx，不能将 CR1000A 的 NSS 无线配置用于 SBE1V1K。设备树另为 SBE1V1K 指定 `cma=256M`；构建保留该上游硬件设置，不用删驱动代替设备树评估。

来源：[设备树](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/dts/ipq9570-sbe1v1k.dts)、[网口与无线初始化](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/ipq95xx/base-files/etc/board.d/02_network)、[无线固件](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/package/firmware/ath12k-firmware/Makefile)、[ath12k 编译定义](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/package/kernel/mac80211/ath.mk)、[NSS 目标限制](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/package/qca-nss/nss-wifi-drv/Makefile)。

## 无线初始设置

`owrt` 原始无线生成脚本会默认启用无线，并填入预设国家、SSID 和通用口令；因此不能描述为“上游初始禁用”。本编译仓库将新生成配置的初始策略调整为无线禁用、SSID 为 `SBE1V1K`、不提供国家兜底值或通用口令，并保留按频段计算的原生加密默认值。启用前由使用者设置实际国家/地区、安全模式和口令；已有无线配置与 provision 数据不被覆盖。该调整属于构建仓库的明确定制，设备树与射频校准数据仍采用 `owrt` 原生实现。

来源：[owrt 无线配置生成脚本](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc)。

## 镜像与安装边界

上游设备采用 `Device/FitImage` 与 `Device/EmmcImage`，生成 initramfs、sysupgrade 和 factory 镜像。`factory.bin` 的构建流程只包含 rootfs 追加与对齐，它不是原厂 Web 刷机格式的承诺。

原生升级逻辑使用 eMMC 分区 `0:HLOS`、`rootfs` 和 `rootfs_data`。这些名称不代表可以在未知安装状态下直接手动写入；升级必须符合该设备的安装状态与官方流程。

首次支持提交给出的安装流程需要串口和 eMMC glitch，并明确要求完整备份 eMMC。该操作可能损坏或覆盖 bootloader。尤其在 glitch 后 eMMC 访问异常时，从 U-Boot 保存环境可能写错闪存位置；上游要求持久环境修改在 Linux 中进行。原厂系统再次完整启动还可能恢复默认 U-Boot 环境。

本仓库仅制作固件，不执行设备刷写，不提供危险的通用写盘或 U-Boot 命令。首次安装、已有系统升级和恢复应分别参照设备官方文档，确认适用的硬件与安装状态。

来源：[owrt 镜像构建实现](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/image/Makefile)、[owrt eMMC 升级实现](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/ipq95xx/base-files/lib/upgrade/platform.sh)、[官方设备页](https://openwrt.org/toh/askey/sbe1v1k)、[官方支持提交内的安装说明](https://github.com/openwrt/openwrt/commit/31c49dd07660a8c9a3b8a34f6fb66ec37244c948)。此次直接读取 Wiki 被 Anubis 拒绝；以上安装事实以官方源码提交为核验依据。

## 支持与验证限制

- `owrt` 使用定制无线固件和内核补丁；官方 OpenWrt 或其他分支的成功报告、已知问题和修复状态不能直接代表本版本。需要针对产物记录实际源码提交和实机表现。
- 包含 PPE 驱动及 ath12k direct-switch 支持，不能替代吞吐、稳定性或流量实际卸载的测试；本仓库不据软件包选择声称已经达到硬件转发性能。
- 静态检查只验证仓库规则、脚本和工作流结构；配置检查只验证所选目标与软件包能否解析；完整编译成功证明产物生成。以上均不等同于实机启动、四网口、三频无线、温控、恢复或升级验证。
- 本文不声称本仓库固件已经完成实机验证。下载后应核对 `sha256sums`，并结合本次运行日志、源码提交与构建记录判断具体版本。

OpenWrt 于 2026-08-23 合入 [SBE1V1K 支持提交](https://github.com/openwrt/openwrt/commit/31c49dd07660a8c9a3b8a34f6fb66ec37244c948)，其官方 snapshot 也已有对应镜像；本仓库实际使用的是源自 VIKINGYFY 的 `yjy116/immortalwrt:owrt`，仍需独立完成构建与设备验证。
