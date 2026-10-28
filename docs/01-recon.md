# 01 · 侦察与目标画像

## 目标与约束

分析对象是一个 IPA 归档。目标不是恢复完整源代码，而是回答三个具体问题：

1. 哪些函数负责常规广告的加载与展示？
2. 哪些回调决定“观看完成后解锁”的业务状态？
3. 哪个字段和条件分支决定更新提示是否不可关闭？

整个过程优先采用静态分析。运行行为只在重新签名后的本地安装版本中进行验证，静态结论与运行结论分别记录。

## 样本身份

| 属性 | 值 |
| --- | --- |
| IPA SHA-256 | `76ea63f1190f699e9d5cada0f7987264d88a93dd3964967c87e4cad9ef28d3f1` |
| 主程序路径 | `Payload/Player.app/Player` |
| 主程序大小 | `68,633,456` 字节 |
| 主程序 SHA-256 | `22ffcd8a53ca28eceb4277cfbb8de0319c97c731e2a7ff9a2ae0ed5851719819` |
| 架构 | ARM64 |
| Mach-O 类型 | 64-bit little-endian |
| 加密标志 | `cryptid = 0` |

补丁器使用主程序 SHA-256，而不是只使用 IPA 哈希。不同压缩工具可能改变 ZIP 层面的字节布局，但待修改的 Mach-O 必须与分析样本完全一致。

## 包体清点

IPA 共包含1029个归档项，核心结构为：

```text
Payload/
└── Player.app/
    ├── Player
    ├── Info.plist
    ├── Frameworks/
    ├── *.bundle
    └── resources
```

第三方广告 SDK 与应用自身业务代码同时存在。仅凭 Framework 名称不能判断实际展示路径，因此后续分析以主程序中的回调实现与交叉引用为准。

## Mach-O 映射

主程序的 `__TEXT` 从虚拟地址 `0x100000000` 开始，文件偏移为0。在本样本的主要代码区内，可将分析地址换算为：

```text
file_offset = virtual_address - 0x100000000
```

该关系只适用于已经确认映射关系的 segment，不能无条件推广到任意 Mach-O 或未映射区间。

关键 section 包括：

- `__TEXT,__text`：ARM64 代码
- `__TEXT,__cstring`：C 字符串
- `__TEXT,__swift5_reflstr`：Swift Reflection 字段名
- `__TEXT,__swift5_fieldmd`：Swift 字段描述
- `__DATA,__objc_classlist`：Objective-C 类列表
- `__DATA,__objc_const`：类只读元数据
- `__DATA,__objc_ivar`：ivar offset 存储

## Objective-C 与 Swift 元数据恢复

通过解析 `class_t`、`class_ro_t`、method list 与 ivar list，恢复出关键类和方法：

### MainViewController

```text
_TtC6Player18MainViewController
├── viewDidLoad
├── viewDidAppear:
├── applicationDidBecomeActive
├── interstitialAdDidLoad:
├── interstitialAdDidClose
└── interstitialAdDidFailToLoad:error:
```

关键 ivar：

| 字段 | 实例偏移 |
| --- | ---: |
| `intersititialAd` | `0x08` |
| `isCheck` | `0x10` |
| `isUpdate` | `0x11` |
| `isLoadAds` | `0x12` |
| `isShowNotice` | `0x13` |

### AppVersion

```text
_TtC6Player10AppVersion
```

| 字段 | 实例偏移 |
| --- | ---: |
| `enable` | `0x10` |
| `dissableMsg` | `0x18` |
| `versionCode` | `0x28` |
| `versionName` | `0x30` |
| `updateInfo` | `0x40` |
| `updateList` | `0x50` |
| `forceUpdate` | `0x60` |

`forceUpdate` 的偏移与指令 `LDRB W8, [X8,#0x60]` 相互印证，使字段名、对象布局和机器指令形成完整证据链。

### UpdateAlert

```text
_TtC6Player11UpdateAlert
├── closeButtonClick
├── linkButtonTapped:
├── initWithFrame:
└── .cxx_destruct
```

该类同时包含 `cancelCallback`、`linkURLStrings` 与 `appVersion` 等字段，为更新弹窗和取消路径的关联提供了额外证据。

## 侦察结论

- 常规广告可以从明确的 delegate callback 入口切断。
- 激励业务必须保留 reward 与 close 回调，不能只阻止播放器展示。
- 强更行为由 `AppVersion.forceUpdate` 的单个条件分支决定，可在不破坏配置请求的情况下进行局部降级。

