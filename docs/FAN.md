# SBE1V1K 风扇控制

两种固件均选择本仓库的 `luci-app-sbe1v1k-fan`，入口为 **系统 → 风扇控制**。它适配 SBE1V1K 的 `pwm-fan` 和 `top-glue-thermal`，提供温度、PWM 占空比、内核档位与四档自动温控阈值设置。

默认使用设备树的原生温控。启用“自定义温度阈值”后，保存并应用会立即修改四个风扇 active trip，并将设置保存到 UCI；重启后由启动脚本应用一次。取消自定义并保存应用会恢复当前设备树的默认阈值，**不表示关闭风扇**。插件不运行调速守护进程，始终由内核 `step_wise` 温控控制 PWM。

当前 `owrt` 设备树的对应关系如下；实际界面从正在运行的设备树读取，未将它们当作固定的 sysfs 编号。

| 内核档位 | active 阈值 | PWM 值 | 占空比 |
| --- | --- | --- | --- |
| 0 | 40°C | 36 / 255 | 约 14% |
| 1 | 50°C | 72 / 255 | 约 28% |
| 2 | 65°C | 128 / 255 | 约 50% |
| 3 | 80°C | 255 / 255 | 100% |

阈值必须按档位递增，最高阈值必须低于实际 hot / critical 保护温度。回差和保护温度只读，不提供任意手动 PWM 或停转设置。当前 SBE 设备树没有测速中断配置，界面显示 PWM 占空比，不提供实测 RPM；两者不能等同。

## 适配依据

联网检索的通用 `luci-app-fancontrol` / `fancontrol` 会直接操作 hwmon PWM。Linux 的 `pwm1_enable` 控制 PWM 和供电行为，不会解除 thermal cooling device 控制，所以不能仅靠设置它避免两套控制同时写 PWM。本插件使用内核支持的温度阈值接口，无需修改 SBE 设备树或内核。

- [SBE1V1K 设备树及四档 cooling-map](https://github.com/yjy116/immortalwrt/blob/a8d4a44c8ede4c703e8866fbf709b34dd1506294/target/linux/qualcommbe/dts/ipq9570-sbe1v1k.dts)
- [Linux thermal_of.c：DT trip 温度可写标志](https://github.com/gregkh/linux/blob/v6.18.55/drivers/thermal/thermal_of.c)
- [Linux thermal_sysfs.c：权限与修改后温控更新](https://github.com/gregkh/linux/blob/v6.18.55/drivers/thermal/thermal_sysfs.c)
- [thermal sysfs 接口](https://docs.kernel.org/driver-api/thermal/sysfs-api.html)
- [pwm-fan 接口及可选 RPM](https://docs.kernel.org/hwmon/pwm-fan.html)
- [ImmortalWrt 通用 LuCI 风扇插件](https://github.com/immortalwrt/luci/tree/master/applications/luci-app-fancontrol)

实际检查既有 WiFi 固件内嵌 DTB，`top-glue-thermal` 有 **7 个 trip**，其中还有继承的 125°C critical，以及本设备的 110°C critical 和 100°C hot。因此插件按类型、设备树 phandle / cooling-map 和运行时 cooling-device 关联识别四个 active trip，不按固定索引或当前温度大小猜测档位。hot / critical、thermal mode、governor 与回差均不写入。

上述提交和内核版本用于记录调查证据，不锁定后续构建。主源码仍逐次跟随 `yjy116/immortalwrt:owrt`。本地插件随本 CI 仓库维护；`ci-local-packages.json` 保存参与构建的文件 SHA256，与外部插件的分支来源记录分开。

## 验证范围

自动测试覆盖设备关联、阈值顺序、原生恢复、保护节点不被改动、写入与持久化错误。构建流程还检查配置选项保留及最终 manifest 确实包含插件。运行时发现不支持的硬件布局或写入失败会明确报错，不能用模拟成功替代实际应用。

这不等同于实机验证。目前没有本设备的实机温控、风扇噪声、长期温度或重启读回证据。
