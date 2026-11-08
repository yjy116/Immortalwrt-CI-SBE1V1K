# 常用插件来源

来源按 CR1000A 参考仓库中实际启用的通用插件对齐。设备专用修补不移植；USB 打印等无接口可用的应用不选，但允许源码默认的 USB 驱动及自动挂载依赖。参考脚本中仅拉取但未启用的其他插件不全部加入固件。

下表各仓库都在每次新运行时解析分支最新提交。单次运行保存快照以保证 WiFi / 无 WiFi 使用同一批外部插件，下一次运行重新解析。完整清单由 [packages.json](../Config/packages.json)维护。

| 插件 | 仓库 | 分支 |
| --- | --- | --- |
| HomeProxy / sing-box、UPnP 配对、GecoosAC、WOLUltra | [VIKINGYFY/packages](https://github.com/VIKINGYFY/packages) | main |
| Vantage | [anothaDev/luci-theme-vantage](https://github.com/anothaDev/luci-theme-vantage) | main |
| Aurora / 设置 | [eamonxg/luci-theme-aurora](https://github.com/eamonxg/luci-theme-aurora)、[luci-app-aurora-config](https://github.com/eamonxg/luci-app-aurora-config) | master |
| Footstrap | [VizzleTF/luci-theme-footstrap](https://github.com/VizzleTF/luci-theme-footstrap) | main |
| Nikki / mihomo-meta | [nikkinikki-org/OpenWrt-nikki](https://github.com/nikkinikki-org/OpenWrt-nikki) | main |
| PassWall | [Openwrt-Passwall/openwrt-passwall](https://github.com/Openwrt-Passwall/openwrt-passwall) | main |
| OpenClash | [vernesong/OpenClash](https://github.com/vernesong/OpenClash) | dev |
| DAE / DAED | [kenzok8/openwrt-daede](https://github.com/kenzok8/openwrt-daede) | main |
| Honk / Doona | [kenzok8/openwrt-honk](https://github.com/kenzok8/openwrt-honk) | main |
| Mini DiskManager | [4IceG/luci-app-mini-diskmanager](https://github.com/4IceG/luci-app-mini-diskmanager) | main |
| 分区扩容 | [sirpdboy/luci-app-partexp](https://github.com/sirpdboy/luci-app-partexp) | main |
| NATMapT / STUN | [muink/openwrt-natmapt](https://github.com/muink/openwrt-natmapt)、[openwrt-stuntman](https://github.com/muink/openwrt-stuntman)、[luci-app-natmapt](https://github.com/muink/luci-app-natmapt) | master |
| qBittorrent / Qt6 / libtorrent | [sbwml/luci-app-qbittorrent](https://github.com/sbwml/luci-app-qbittorrent) | master |
| DDNS-Go | [sirpdboy/luci-app-ddns-go](https://github.com/sirpdboy/luci-app-ddns-go) | main |
| Tailscale 界面 | [asvow/luci-app-tailscale](https://github.com/asvow/luci-app-tailscale) | main |
| EasyTier | [EasyTier/luci-app-easytier](https://github.com/EasyTier/luci-app-easytier) | main |
| Lucky | [gdy666/luci-app-lucky](https://github.com/gdy666/luci-app-lucky) | main |
| geodata 更新器 | [yjy116/Immortalwrt-CI-CR1000A-OWRT](https://github.com/yjy116/Immortalwrt-CI-CR1000A-OWRT/tree/main/package/v2ray-geodata-updater) | main |

AdGuard Home、Samba4、SQM、WireGuard、ZeroTier、SoftEther、统计工具等继续由源码配置的官方 feeds 提供。Tailscale 核心使用 packages feed，init/config 由 asvow 界面包提供，与参考的文件归属调整一致。UPnP 核心与界面使用同一个 VIKINGYFY/packages 提交，不覆写其配方。

SBE1V1K 自带风扇，额外使用本仓库维护的 [`luci-app-sbe1v1k-fan`](../packages/luci-app-sbe1v1k-fan)；这属于设备适配，不以 CR1000A 的插件集合判断是否需要。它配置原生四档温控阈值，不安装通用 `fancontrol` 调速守护进程。文件校验值记录在 `ci-local-packages.json`，行为及来源见 [风扇说明](FAN.md)。

DAE / DAED 沿用参考仓库的统一后端、互斥、迁移与 geodata 整合，补丁针对当前分支重新制作，并验证真实 shell / JavaScript 逻辑。Honk 保留上游启动、停止、重启及初始化逻辑；主动重启可以开启已关闭的服务。设备正常启动按保存的 enabled 状态处理。Doona 随 Honk 服务提供，不额外设置开机服务。

Honk 增加一处共存补丁：回收共享 `dae0` / `dae0peer` / `daens` 前检查 DAE/DAED；它们仍在运行或进程探测失败时，拒绝删除这些资源并报告错误。无人占用时仍使用上游的残留回收流程。此补丁不修改 enabled、初始化或启停开关语义；用于修复上游新增回收逻辑可能破坏另一后端网络的问题，补丁及摘要记录于 `ci-backend-components.json`。

Honk 回归检查执行集成后的真实 init、RPC 和 lifecycle 脚本，验证资源回收后再启动、活动后端资源不被删除，以及失败返回和开关状态恢复。测试只替换路由器 I/O 与等待边界；该检查不代表路由器上的实际进程、网络或 BPF 验证。

“跟随插件分支”指更新打包配方；配方中组件提交、版本或发布归档的校验值仍由插件维护者选择。CI 保留这些值，记录到 `ci-backend-components.json`，不使用参考仓库旧版本的固定 Honk 生成配方覆盖当前分支。`ci-package-integration.json` 记录 UPnP 配对和 Tailscale 文件归属证据。
