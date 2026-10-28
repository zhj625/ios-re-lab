# 02 · 关键控制流恢复

## 常规展示路径

常规广告入口包括启动页、个人页 banner/native 和主页 interstitial。对这类路径，需要区分“展示函数”和“展示关闭后的页面转场”。

启动页不能直接在入口 `RET`，否则可能同时跳过应用进入主界面的正常转场。最终方案从 `SplashViewController.viewDidAppear:` 跳转到应用原有的 `splashAdDidClose` 公共路径：

```text
viewDidAppear
    ├── load/present splash
    └── splashAdDidClose
            └── normal app transition
```

个人页 banner/native 与主页 interstitial 的 didLoad callback 只负责挂载或展示广告，因此可在其函数入口返回。

## 激励业务路径

11个业务控制器具有相似结构：

```text
didLoad
  └── show rewarded video

didReward
  └── unlock/continue business action

didClose
  └── dismiss, refresh and restore UI

didFailToLoad
  └── failure message or blocked state
```

如果只让 `didLoad` 返回，业务不会解锁；如果只让 `didFailToLoad` 返回，用户仍停留在等待状态。因此补丁采用以下控制流：

```text
didLoad or didFailToLoad
          │
          ▼
      didReward
          │
          ▼
      didClose
```

覆盖的业务类：

1. `DownloadItem`
2. `ComicDetail`
3. `Video`
4. `AdRemoval`
5. `ReadAds`
6. `ComicPlay`
7. `MusicAds`
8. `ReadDetail`
9. `PanFolder`
10. `BookAds`
11. `Player`

## ARC 与寄存器语义

原 didLoad wrapper 保存 `X19/X20` 并持有 controller 与 ad object。改变调用目标后，需要同步调整：

- 删除不再需要的 controller retain；
- 将 reward handler 的 self 参数放入 `X0`；
- 对原 ad object 使用 `swift_bridgeObjectRelease`；
- 将 controller 重新放回 `X0`；
- 尾调用正常 close handler。

核心伪代码：

```c
void patched_didLoad(Controller *self, BridgeObject ad) {
    reward_handler(self);
    swift_bridgeObjectRelease(ad);
    close_handler(self);
}
```

这不是原始 Swift 源代码，而是根据 ARM64 调用约定、寄存器使用和运行库调用恢复出的等价语义。

## 强制更新路径

关键指令：

```asm
LDRB W8, [X8,#0x60]       ; AppVersion.forceUpdate
TBNZ W8, #0, forced_path  ; true => skip dismissible setup
```

false 路径会构造普通更新提示和取消相关逻辑，之后与强制路径重新汇合。true 路径直接跳过这段设置，导致用户无法关闭弹窗继续使用。

补丁将 `TBNZ` 替换为 `NOP`：

```asm
LDRB W8, [X8,#0x60]
NOP
```

这样无论服务端字段值为何，都会执行可关闭提示的设置，然后继续进入公共展示路径。配置下载、版本内容和更新链接均不受影响。

## 为什么不修改网络请求

阻断整个配置请求会同时影响广告配置、内容源和其他远端参数，并可能触发错误恢复逻辑。局部修改最终决策分支的影响范围更小，也更容易验证。

