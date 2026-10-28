# Security and artifact policy

## Repository contents

本仓库不接收或分发以下内容：

- 原始或修改后的 IPA/App 包
- 第三方 Mach-O、Framework 或资源包
- 证书、私钥、Provisioning Profile
- 账号、Token、Cookie 或设备标识

提交问题时请只提供必要的哈希、脱敏日志、指令片段和最小复现信息。

## Version safety

补丁器通过完整主程序 SHA-256 与逐补丁 preimage 双重限制目标版本。不要通过删除这些检查来支持未知版本；应重新分析新版本并生成新的偏移和期望字节。

## Runtime boundary

重新打包会使原 Mach-O 代码签名失效。签名、安装和运行测试应在使用者自己控制的设备与环境中完成。

