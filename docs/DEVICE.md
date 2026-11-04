# SBE1V1K 设备与构建说明

核验日期：2026-11-04。设备别名为 Askey SBE1V1K、Spectrum SBE1V1K、Askey RTQ7300T。

## 源码依据

本仓库使用 ImmortalWrt `master` 的原生设备支持，默认提交为 `89f1ef18c888f841633f19f92655ee4b7f7716a4`。OpenWrt 已于 2026-08-23 合入 [SBE1V1K 支持提交](https://github.com/openwrt/openwrt/commit/31c49dd07660a8c9a3b8a34f6fb66ec37244c948)；声称该支持 PR 尚未合并的早期指南已过时。

核验时，OpenWrt 和 ImmortalWrt 的 `openwrt-25.12` 分支均没有 `askey_sbe1v1k` 设备定义。不能仅将本仓库源码分支改为稳定分支并假定兼容。使用其他 `SOURCE_REF` 时，必须重新检查设备配置与所选软件包。

| 编译项 | 值 |
| --- | --- |
| Target / Subtarget | `qualcommbe/ipq95xx` |
| Device profile | `askey_sbe1v1k` |
| 软件包架构 | `aarch64_cortex-a53` |
| 锁定源码的内核系列 | Linux 6.18 |
| Device tree | `ipq9570-sbe1v1k.dts`，包含 `ipq9574.dtsi` |

对应配置符号为 `CONFIG_TARGET_qualcommbe`、`CONFIG_TARGET_qualcommbe_ipq95xx` 和 `CONFIG_TARGET_qualcommbe_ipq95xx_DEVICE_askey_sbe1v1k`。

来源：[设备镜像定义](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/image/ipq95xx.mk)、[target 定义](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/Makefile)、[25.12 设备列表](https://github.com/immortalwrt/immortalwrt/blob/openwrt-25.12/target/linux/qualcommbe/image/ipq95xx.mk)。

## 硬件与原生配置

| 项目 | 设备定义 |
| --- | --- |
| SoC | Qualcomm IPQ9570 |
| 内存 / 存储 | 2 GB RAM / 8 GB eMMC |
| WAN | `wan`：10GbE，RTL8261BE |
| LAN | `lan1`：2.5GbE，QCA8081；`lan2`、`lan3`：1GbE，QCA8075 |
| 无线 | 2.4 / 5 / 6 GHz，ath12k / QCN9274 固件与 WSI 多射频支持 |
| 散热 | PWM 风扇与设备树温控策略 |

原生 LAN bridge 包含 `lan1 lan2 lan3`。设备树负责网口、MAC、PCIe、风扇等硬件描述；板级校准脚本从本机 `0:ART` 读取射频校准数据。构建仓库保留这些实现，不替换设备校准数据，不采用 CR1000A 的 ath11k、Q6、NAND 或网口修补。

带无线版本保留原生设备依赖，包括 `ath12k-firmware-qcn9274`、`ipq-wifi-askey_sbe1v1k`、`kmod-ath12k`、`kmod-hwmon-pwmfan`、`kmod-phy-realtek`、`rtl826x-firmware`、`f2fsck` 和 `mkf2fs`。无无线版本按构建配置移除无线功能，不应移除网口、eMMC 或风扇依赖。

无线保持上游初始禁用。启用前应在 LuCI 中选择设备实际使用地的国家/地区，设置适用的安全模式与口令；本仓库不硬编码无线密码或强制国家代码。

来源：[设备树](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/dts/ipq9570-sbe1v1k.dts)、[网口与无线初始化](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/ipq95xx/base-files/etc/board.d/02_network)、[ART 校准处理](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/ipq95xx/base-files/etc/hotplug.d/firmware/11-ath12k-caldata)。

## 镜像与安装边界

上游设备采用 `Device/FitImage` 与 `Device/EmmcImage`，生成 initramfs、sysupgrade 和 factory 镜像。`factory.bin` 的构建流程只包含 rootfs 追加与对齐，它不是原厂 Web 刷机格式的承诺。

原生升级逻辑使用 eMMC 分区 `0:HLOS`、`rootfs` 和 `rootfs_data`。这些名称不代表可以在未知安装状态下直接手动写入；升级必须符合该设备的安装状态与官方流程。

首次支持提交给出的安装流程需要串口和 eMMC glitch，并明确要求完整备份 eMMC。该操作可能损坏或覆盖 bootloader。尤其在 glitch 后 eMMC 访问异常时，从 U-Boot 保存环境可能写错闪存位置；上游要求持久环境修改在 Linux 中进行。原厂系统再次完整启动还可能恢复默认 U-Boot 环境。

本仓库仅制作固件，不执行设备刷写，不提供危险的通用写盘或 U-Boot 命令。首次安装、已有系统升级和恢复应分别参照设备官方文档，确认适用的硬件与安装状态。

来源：[镜像构建实现](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/image/Makefile)、[eMMC 升级实现](https://github.com/immortalwrt/immortalwrt/blob/89f1ef18c888f841633f19f92655ee4b7f7716a4/target/linux/qualcommbe/ipq95xx/base-files/lib/upgrade/platform.sh)、[官方设备页](https://openwrt.org/toh/askey/sbe1v1k)、[官方支持提交内的安装说明](https://github.com/openwrt/openwrt/commit/31c49dd07660a8c9a3b8a34f6fb66ec37244c948)。此次直接读取 Wiki 被 Anubis 拒绝；以上安装事实以官方源码提交为核验依据。

## 支持与验证限制

- 核验时，上游 [#24949](https://github.com/openwrt/openwrt/issues/24949) 仍为 open，记录 ath12k / WSI 多射频偶发初始化失败；[#24370](https://github.com/openwrt/openwrt/issues/24370) 仍为 open，记录多 radio 频段与索引对应变化。构建成功不证明这些问题已解决。
- 最新 OpenWrt main 于 2026-11-01 增加 [PWM 状态灯与风扇转速](https://github.com/openwrt/openwrt/commit/9e881bc5befdef5bda37208a62aac11c2282a15e) 和 [EFR32MG21 UART](https://github.com/openwrt/openwrt/commit/a939b3fbfd8d19503bed77c831a63c130ef4fd3b) 支持。本仓库默认锁定的 ImmortalWrt 提交尚未包含这两项，不声称支持这些新增功能。
- 静态检查只验证仓库规则、脚本和工作流结构；配置检查只验证所选目标与软件包能否解析；完整编译成功证明产物生成。以上均不等同于实机启动、四网口、三频无线、温控、恢复或升级验证。
- 本文不声称本仓库固件已经完成实机验证。下载后应核对 `sha256sums`，并结合本次运行日志、源码提交与构建记录判断具体版本。

OpenWrt 官方 [snapshot profiles.json](https://downloads.openwrt.org/snapshots/targets/qualcommbe/ipq95xx/profiles.json) 已列出该设备的原生镜像；这只能证明官方构建已有对应产物，不能替代本仓库的编译和设备测试。
