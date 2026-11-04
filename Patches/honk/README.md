# Honk / Doona 原生服务控制

源仓库跟随 [kenzok8/openwrt-honk 的 main](https://github.com/kenzok8/openwrt-honk/tree/main)。首次核验提交为 `036d31fc9d0c30fca12501f22960529c7f6b97fd`；构建使用当次分支提交，不固定此 SHA。Honk 与 Doona 的版本、不可变资源标签和 SHA-256 均保留上游当前配方，不生成旧版本覆盖文件。

管理页面：`服务 → Honk → 概览`，路径 `/cgi-bin/luci/admin/services/honk/overview`。

本仓库不修改 Honk 的 UI、服务和 RPC 逻辑，保留上游“启动 / 停止 / 重启”操作：

- 默认 `enabled=0`、`initialized=0`，不会启动。完成初始化后仍需显式开启。
- 手动启动、RPC 重启允许写入 `enabled=1`；已初始化时设备重启允许自动启动。
- 成功停止会保存 `enabled=0`，设备开机不会自动运行；手动启动或重启仍可重新开启。
- 原生 init 的 `restart/reload` 本身不更改 `enabled`，启动阶段依然检查 `enabled` 和 `initialized`。它与 LuCI/RPC 重启的入口语义不同。
- 保留上游错误处理和回滚：例如停止失败会报错并恢复此前的 `enabled`，不会把失败报告为已停止。

Doona 是 Honk 原生 API 提供的静态管理页面，不是另一个守护进程，随 Honk 启停。旧 `boot_enabled` 配置项在当前上游中已不控制独立自启行为，开机是否启动以 `enabled` 和初始化状态为准。

集成仅检查上游组件配方、默认状态和真实 init/RPC 分支行为，并交叉验证 UI 到 RPC 的操作入口。未添加 Honk 补丁，不删除用户配置或账户。路由器 I/O 使用测试夹具，未进行实机 BPF 验证。DAE/DAED 一侧的共享资源互斥补丁继续保留。
