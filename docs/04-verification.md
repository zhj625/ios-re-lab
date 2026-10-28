# 04 · 验证、边界与复现

## 验证层级

本项目将验证分为三层，避免把静态推断描述成运行事实。

### 1. 静态验证

- 主程序 SHA-256 与分析样本一致；
- 每处文件偏移处的原始指令与 preimage 一致；
- `B/BL` 目标地址对齐且在可编码范围内；
- 修改前后指令长度相同；
- reward/close 目标属于对应控制器的已恢复回调；
- `forceUpdate` 字段偏移与 Swift 元数据一致。

### 2. 构建验证

- 输出 IPA 可以被 ZIP 解析；
- `ZipFile.testzip()` 无损坏项；
- 输入与输出均包含1029个相同路径；
- 逐文件比较确认只有 `Payload/Player.app/Player` 改变；
- 输出主程序和 IPA 重新计算 SHA-256；
- 与上一版已验证构建对比时，强更版本只新增4字节差异。

最终整合构建的记录值：

| 产物 | SHA-256 |
| --- | --- |
| 修改后主程序 | `432eb181b95e712e83b1958b3b5e6184cb5a094b147c7f153214746d80fa091f` |
| 修改后 IPA | `fe1387194fc2ad3608a8dd9495b07d56db161e82e542f30a17ca08f6b84f107a` |

这些哈希用于确认本次构建记录；对应修改版 IPA 已作为 GitHub Release 资产发布，原始 IPA 不在仓库中。

### 3. 运行验证

已完成：

- 重新签名与安装；
- 应用正常启动；
- 常规广告路径不再展示；
- 激励业务无需完成视频展示即可继续；
- 页面关闭与业务状态恢复正常；
- 服务端真实触发强制更新后，更新提示可正常关闭；
- 关闭更新提示后应用能够继续使用，未再被强制更新流程阻断。

强更补丁已完成字段与分支定位、构建差异检查、重新签名安装以及真实服务端触发条件下的端到端运行验证。

## 本地集成验证示例

以下命令只展示流程，原始 IPA 不在仓库中：

```bash
python src/patch_ibox_250.py input.ipa output.ipa
python -m unittest discover -s tests -v
```

可使用以下 Python 逻辑验证归档：

```python
import zipfile

with zipfile.ZipFile("output.ipa") as archive:
    assert archive.testzip() is None
    assert "Payload/Player.app/Player" in archive.namelist()
```

## 已知边界

- 固定偏移只适用于记录的主程序哈希。
- 应用后端协议或内容接口停用时，客户端补丁无法恢复服务端能力。
- 新编译器版本可能改变 Swift 对象布局和 ARC 优化方式。
- 重新打包必然使原代码签名失效。
- 静态分析无法覆盖所有设备、系统版本和网络状态。

## 回滚

补丁器从不覆盖输入文件，并拒绝目标路径与源路径相同。回滚只需删除输出 IPA，继续使用原始归档；无需对源文件执行反向补丁。
