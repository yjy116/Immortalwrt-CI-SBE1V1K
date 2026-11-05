# ImmortalWrt CI · SBE1V1K

为 Askey / Spectrum **SBE1V1K（RTQ7300T）** 编译 ImmortalWrt 固件的 GitHub Actions 仓库。参考 [Immortalwrt-CI-CR1000A-OWRT](https://github.com/yjy116/Immortalwrt-CI-CR1000A-OWRT)，使用同一源码分支 [yjy116/immortalwrt:owrt](https://github.com/yjy116/immortalwrt/tree/owrt)，其直接上游为 [VIKINGYFY/immortalwrt:owrt](https://github.com/VIKINGYFY/immortalwrt/tree/owrt)。设备目标为 `qualcommbe/ipq95xx`。

## 默认设置

| 项目 | 配置 |
| --- | --- |
| 管理地址 | `192.168.70.1` |
| 主机名 | `SBE1V1K` |
| 管理用户 | `root`，无预设密码；首次登录后设置 |
| 无线 | 本仓库设置初始禁用；启用前设置实际国家/地区与加密口令 |
| 主题 | Vantage |
| 源码 | 每次构建跟随 `yjy116/immortalwrt:owrt` 最新提交 |

源码地址和分支记录在 [Config/source.json](Config/source.json)，不固定主源码提交。你同步 `yjy116/immortalwrt:owrt` 后，下一次运行会使用更新后的分支。一次运行先解析最新提交，再让 WiFi / 无 WiFi 两个任务使用该次解析的同一源码版本，避免构建期间分支更新造成版本不一致；实际 SHA 写入产物供追溯。

常用插件及来源已按参考仓库对齐，包括 HomeProxy、PassWall、OpenClash、Nikki、DAE / DAED、Honk / Doona、qBittorrent、AdGuard Home、DDNS-Go、Lucky、Tailscale、EasyTier、NATMapT、SQM、UPnP、ttyd、Samba4、WireGuard、ZeroTier、磁盘管理、WOLUltra 和流量统计；主题包括 Vantage、Aurora 和 Footstrap。具体来源与分支见 [插件说明](docs/PLUGINS.md)。

SBE1V1K 没有外露 USB 接口，不选择 USB 打印、手机互联等应用。USB 内核驱动、`automount` 及其依赖保留源码原生默认，不为剔除它们维护补丁或额外构建限制。保留服务于板载 eMMC 的磁盘和文件系统工具；依据见 [设备说明](docs/DEVICE.md)。

Honk 保留上游的启动、停止、重启操作。停止会保存关闭状态，正常设备启动不会擅自开启；主动点击启动或重启允许开启服务。Doona 由同一 Honk 服务提供。首次使用仍需完成上游要求的初始化。

两种固件均加入 SBE1V1K 专用的 **系统 → 风扇控制** 页面。默认沿用原生自动温控，也可保存四档温度阈值并在重启后应用；关闭自定义会恢复设备树默认值。PWM 仍由内核控制，高温保护保持不变，详见 [风扇插件说明](docs/FAN.md)。

## 开始编译

1. 打开本仓库的 [Actions](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions)，选择 `SBE1V1K.yml` 对应的编译工作流。
2. 点击 **Run workflow**，按下表选择参数。
3. 完成后从该次运行的 **Artifacts** 下载结果；完整固件构建启用 `PUBLISH` 时也会发布到 [Releases](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/releases)。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `WIFI_MODE` | `both` | `both` 同时构建带无线与无无线版本；`yes` 仅带无线；`no` 仅无无线 |
| `CONFIG_ONLY` | `false` | 为 `true` 时只解析并验证配置、保存配置与来源记录，不编译固件或发布 Release |
| `PUBLISH` | `true` | 完整固件构建成功后发布 Release |

带无线版本使用 owrt 的 ath12k 驱动、`ath12k-firmware-qcn9274-ddwrt` 固件及 SBE1V1K 板级数据。两种版本均保留原生 QCOM PPE、eMMC 和风扇依赖。无无线版本用于有线路由用途。构建保存实际源码提交，便于定位结果；分支更新后，不同运行会得到不同源码。

该 owrt 源本身预设无线开启、国家代码与共享口令。本仓库修改首次生成的无线默认值：SSID 为 `SBE1V1K`、初始禁用、不预置共享口令或固定国家代码；已有无线配置继续由上游检测逻辑保留。CI 仓库分支为 `main`，固件源码分支为 `owrt`，请勿混淆。

无无线版本移除 ath12k 驱动及对应固件，不修改设备树或回收无线保留内存。`192.168.70.1` 是新安装或恢复默认后的地址；保留旧配置升级时，已有 LAN 地址通常继续生效。

`CHECK.yml` 在 push / pull request 时执行仓库静态验证。配置检查、完整固件编译和实机测试是不同验证阶段；不能互相替代。

## 编译缓存

完整构建使用与 CR1000A 相同范围的缓存：`.ccache`、`staging_dir/host` 和 `staging_dir/toolchain-*`。冷构建先在独立步骤编译工具与工具链，成功后立即保存预热缓存；即使后面的插件编译失败，下次仍可复用这部分。整轮产物验证成功后再保存含最新 `.ccache` 的完整缓存。

缓存兼容键包含工具/工具链/目标源码树、展开后的有效配置、构建脚本、主机系统/架构/编译器和构建路径。普通源码提交或插件版本更新不会仅因 SHA 改变而废弃缓存；涉及上述兼容条件的变化会重新预热。缓存恢复仍从当次最新源码和插件分支构建，不会把旧固件直接当成新结果。

日志沿用 CR1000A 的常规简洁输出。固件并行编译失败时，明确提示后以 `make -j1 V=s` 再编译并输出详细诊断；如果第二次仍失败，任务会失败。`build-logs-wifi-*` Artifact 保留预热、下载、首次编译和存在时的详细重试日志。

完整构建会先清理 GitHub 临时 Runner 中未使用的 Swift、GHCup、CodeQL、Miniconda、Julia、浏览器测试工具、PowerShell 和 Vcpkg 等预装 SDK，系统编译工具和其余工具缓存保留。此清理与工具链安装分别执行，不因清理脚本变化废弃兼容的编译缓存。`runner-storage.log` 记录清理前后的磁盘容量、inode 和实际清理目录大小，`ci-disk.log` 记录固件编译前后状态，均随构建日志上传。

2026-11-05 排查 [41822380302 的 WiFi 失败任务](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions/runs/41822380302/job/126548527295)：GitHub 的检查注释明确记录 Runner 写日志时发生 `No space left on device` 并异常退出，后续日志上传未能执行。无 WiFi 任务及其风扇插件产物校验成功，但不能据此认定两版均成功。新增 SDK 清理与空间记录用于修正这次存储耗尽问题；已丢失的 WiFi 任务日志不能用于推断具体占用目录。

修复后的 [41942365611](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions/runs/41942365611) 已完成双版本编译与发布：[WiFi 版](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/releases/tag/sbe1v1k-wifi-yes-41942365611-1)、[无 WiFi 版](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/releases/tag/sbe1v1k-wifi-no-41942365611-1)。两台 Runner 各额外释放约 13 GiB，编译结束分别剩余约 58 / 60 GiB；两版均实际命中约 235 MB 的工具链预热缓存，跳过重新预热，并在首次并行编译中成功。固件内风扇插件的 11 个安装文件、权限、菜单及 `S99sbe1v1k-fan` 开机链接已实读核验。该次编译 CI 为 `06882596`，实际主源码为 `ec73307670005a1f00cbeb039dc90709fa2a871e`；Linux 仓库检查 110 项通过、无跳过。

每次 Actions Summary 会显示实际恢复的缓存键，产物 `ci-cache.json` 保存兼容性依据。没有缓存的首次编译不会因此立即加速，后续命中才可省去重复的工具链工作；插件自身的 Go/Rust 等构建仍可能耗时。缓存不包含完整 `build_dir`、目标 staging、feeds、下载目录或旧固件。

2026-11-04：[完整构建](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions/runs/41763922900)的 WiFi / 无 WiFi 两个编译任务及产物检查均成功，均未触发详细重试。`ci-compile.log` 分别为 311 / 306 行；完整缓存分别保存约 932 / 891 MB。本轮是冷构建，尚未实测缓存恢复后的提速。

该次运行的旧发布命令遇到权限错误，已通过[独立发布工作流](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/actions/runs/41783824145)使用原 Artifact 成功发布：[WiFi 版](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/releases/tag/sbe1v1k-wifi-yes-41763922900-1)、[无 WiFi 版](https://github.com/yjy116/Immortalwrt-CI-SBE1V1K/releases/tag/sbe1v1k-wifi-no-41763922900-1)。来源为当次解析的 `owrt` 提交 `a8d4a44c8ede4c703e8866fbf709b34dd1506294`；此处仅记录验证结果，不锁定后续构建。尚无实机验证记录。

## 下载文件

发布标题使用 `SBE1V1K-WIFI-YES/NO-yjy116-owrt-日期时间`，固件文件名也包含 `wifi-yes/no` 和日期时间。日期取原构建任务创建时间并转为北京时间，补发时不改成补发日期。Release 标签仍使用 `sbe1v1k-wifi-<mode>-<runid>-<attempt>`，已有发布页链接保持不变；附件下载地址随文件名更新。

发布说明顶部提供三种固件的直接下载链接。每版只有 7 个上传附件：3 个固件、编译配置、软件包 manifest、SHA256 校验表和 `build-records-*.tar.gz`，加上 GitHub 自动生成的两个源码包共 9 项，无需展开隐藏列表就能看到固件。固件内容不变；新校验表对应本页的新文件名。原 `sha256sums`、`SHA256SUMS-CI`、`*.buildinfo`、`profiles.json`、来源记录及包归档完整保存在构建记录压缩包中，`release-files.json` 记录原文件名到发布文件名的对应关系。Actions Artifact 继续保留原始文件名。

启用发布时，运行开始即创建指向本次 CI 提交的标签；发布前再次校验标签，避免长时间编译期间 `main` 更新影响发布权限。`attempt` 使用准备任务输出的构建批次，因此仅重跑失败的发布任务可复用原 Artifact；重跑全部任务则建立新批次。固件先上传到草稿，全部上传成功后才正式发布；上传失败可续传该草稿，已正式发布的版本不会被替换。失败构建可能留下没有 Release 的标签。

正在构建的标签需要保留到发布完成。`41942365611` 的两个标签在创建后、发布前缺失，导致首次发布被校验拒绝；恢复为原 CI 提交后，仅重试失败的发布任务即成功，未重新编译。恢复标签时必须核对原任务的完整 CI SHA，不能把标签改指向当时的最新 `main`。

已完成编译但发布失败时，也可运行 `PUBLISH.yml`，填写原构建的 `RUN_ID`、`BUILD_ATTEMPT` 和 WiFi 版本。它会确认原构建成功、核对原 CI 标签、下载并校验原 Artifact，然后使用当前发布脚本重新发布，无需重新编译。原构建的工作流不会因仓库后来更新而改变，因此这个入口也能修复旧运行的发布问题；Artifact 必须仍在保留期内。

| 文件名中的标识 | 用途 |
| --- | --- |
| `initramfs-uImage`（`.itb`） | RAM 启动、首次安装流程与恢复所需镜像 |
| `squashfs-sysupgrade`（`.bin`） | 已按适用流程安装 OpenWrt / ImmortalWrt 后的系统升级 |
| `squashfs-factory`（`.bin`） | 上游生成的 rootfs 镜像，不能按名称推断为原厂 Web 可直接刷入的固件 |

**首次安装涉及设备专用的串口、eMMC 与启动环境操作。** 请先阅读 [设备说明](docs/DEVICE.md) 和其中的官方来源；本仓库不提供一键刷机脚本。编译成功仅证明构建完成，不代表实机启动、网络、无线或升级验证通过。

## 修改配置

在 `Config/` 中调整编译选项，在 `Scripts/defaults.py` 中设置默认 IP、主机名和主题。LAN 地址和主机名只修改上游生成默认值，保留配置升级时不会由本仓库脚本重置。Vantage 首次注册沿用其上游行为，可能切换已有主题。修改后运行静态检查；完整构建会先展开并验证配置，确认所需软件包没有被依赖解析取消。`CONFIG_ONLY=true` 可用于单独诊断，无需每次重复运行。

本地检查：`python3 -m unittest discover -s Tests -v`。Linux CI 对测试设置 60 秒超时，并运行 shell 语法检查与 actionlint。每个显式配置选项均会在 `make defconfig` 后核对，缺包会使任务失败。

主源码跟随 `owrt`，官方 feeds 按源码提供的分支更新，实际 SHA 均记录到产物中。CI 读取源码 fork，由你负责同步 fork；同步后无需修改本仓库的提交配置。`Config/packages.json` 只指定外部插件仓库与分支，不固定其提交。每次新运行解析各插件最新提交，两种版本共享当次解析结果；实际 SHA 保存到 `ci-packages.json`。DAE / DAED、Honk / Doona 的组件版本和校验值沿用当次插件分支的配方，详见 `ci-backend-components.json`；这不表示绕过配方独立追逐内核/UI 开发分支。部分二进制下载配方并无固定内容哈希，因此不宣称完全可复现构建。

只安装选中插件及其递归依赖，外部包的官方 feed / host 依赖列在 `Config/packages.json` 的 `feed_dependencies` 中。不安装无关的软件包集合；Kconfig 输出错误时，即使命令返回零也会使配置验证失败。

请保留 SBE1V1K 的原生设备树、校准数据处理、网口定义和 eMMC 升级逻辑。参考仓库中针对 CR1000A 的设备修补不能直接用于本机型。

## 来源

- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)
- [构建源码 yjy116/immortalwrt:owrt](https://github.com/yjy116/immortalwrt/tree/owrt)
- [直接上游 VIKINGYFY/immortalwrt:owrt](https://github.com/VIKINGYFY/immortalwrt/tree/owrt)
- [OpenWrt SBE1V1K 设备页](https://openwrt.org/toh/askey/sbe1v1k)
- [CR1000A 参考编译仓库](https://github.com/yjy116/Immortalwrt-CI-CR1000A-OWRT)
- [设备适配依据、安装与支持限制](docs/DEVICE.md)
