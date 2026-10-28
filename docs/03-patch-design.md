# 03 · 补丁设计与偏移

## 补丁模型

每个补丁由四部分组成：

```python
Patch(offset, expected, replacement, description)
```

- `offset`：主 Mach-O 中的文件偏移
- `expected`：分析样本的原始指令字节
- `replacement`：等长的新指令字节
- `description`：可审计的修改目的

所有补丁必须等长，工具拒绝改变 Mach-O 布局。这样无需重写 segment、load command、符号表或重定位信息。

## ARM64 跳转编码

`B` 与 `BL` 使用有符号 `imm26`，实际距离单位为4字节：

```text
delta = target - source
imm26 = delta >> 2
B  = 0x14000000 | (imm26 & 0x03ffffff)
BL = 0x94000000 | (imm26 & 0x03ffffff)
```

编码器检查：

- source/target 必须4字节对齐；
- `imm26` 必须处于26位有符号范围；
- 结果使用 little-endian 写入。

## 常规入口

| 文件偏移 | 原始 | 替换 | 目的 |
| ---: | --- | --- | --- |
| `0x00309840` | 函数序言 | `B 0x0030BCB8` | 进入启动广告正常关闭路径 |
| `0x000A01D8` | 函数序言 | `RET` | 阻止 banner 挂载 |
| `0x000A0808` | 函数序言 | `RET` | 阻止 native ad 挂载 |
| `0x0067947C` | 函数序言 | `RET` | 阻止 interstitial 展示 |

## 激励业务模板

每组业务使用7个补丁：

| 相对位置 | 修改 |
| ---: | --- |
| `didLoad + 0x2C` | controller retain → `NOP` |
| `didLoad + 0x34` | show body → reward handler |
| `didLoad + 0x38` | `MOV X0,X20` → `MOV X0,X19` |
| `didLoad + 0x3C` | `swift_release` → `swift_bridgeObjectRelease` |
| `didLoad + 0x40` | `MOV X0,X19` → `MOV X0,X20` |
| `didLoad + 0x4C` | tail release → close handler |
| `didFailToLoad` | 函数入口 → didLoad wrapper |

11组共77处修改。

## 更新策略补丁

| 文件偏移 | 原始字节 | 替换字节 | 原始语义 |
| ---: | --- | --- | --- |
| `0x00C72D44` | `08 14 00 37` | `1F 20 03 D5` | `TBNZ W8,#0,forced_path` → `NOP` |

## 总计

```text
4 regular presentation patches
+ 11 × 7 rewarded-flow patches
+ 1 forced-update patch
= 82 patches
```

## 版本迁移规则

新版本不得复用旧偏移。正确迁移步骤：

1. 记录新主程序 SHA-256；
2. 重新恢复类、字段和 callback；
3. 对比新旧函数控制流；
4. 为每个新位置记录原始指令；
5. 更新目标哈希、偏移和 preimage；
6. 重新执行静态、构建和运行验证。

