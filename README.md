# OpenCode TPS

在 OpenCode（桌面版 / CLI）生成回复时，用一个 68px 浮球显示实时 token 速度；兼容 OpenChamber。

- 插件订阅 OpenCode v2 会话事件，把每个会话的速度写入本地 JSON
- Python/Tkinter 浮球读取状态，空闲自动隐藏
- 多会话合并显示，最多 4 行，顺序按首次出现固定
- 不联网、不读 API Key、无遥测

## 环境

- Windows 10 / 11
- OpenCode 2.x（桌面版 / CLI），或 OpenChamber 2.5+
- Python 3.10+，需要自带 Tkinter

## 安装

从源码：

```powershell
git clone https://github.com/xhj845/opencode-tps.git
cd opencode-tps
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

或从站点下载 `opencode-tps.zip` 后解压安装：

https://openchamber-tps-u1rz4ugx7kj.qoder.website

安装脚本会：

- 把 `plugin/tps-live.js` 复制到 `%USERPROFILE%\.config\opencode\plugins\`
- 把 `app/*.py` 复制到 `%LOCALAPPDATA%\OpenChamberTps`
- 在启动文件夹创建 `OpenCode TPS.lnk`
- 启动后台守护进程

重启一次 OpenCode 或 OpenChamber，然后发一条消息。

> 安装目录沿用 `OpenChamberTps`，以兼容已安装版本。

## 使用

- 单击浮球：展开速度面板
- 单击面板任意位置：收回浮球
- 按住拖动：移动位置，位置会记住
- 右键：展开 / 收起 / 隐藏 30 秒 / 退出监控
- 没有活动会话时自动隐藏

流式阶段显示的是基于增量文本的估算值（前面带 `≈`）；回合结束时用 provider 返回的 token 数校正，显示精确平均速度。

## 工作原理

OpenCode 插件订阅 `session.text.delta` 和推理增量，按会话把 1.5 秒滚动速度写入 `%LOCALAPPDATA%\OpenChamberTps\state-*.json`。Python/Tkinter 悬浮窗读取这些文件并绘制浮球和面板。

OpenChamber 与 OpenCode 共用 `~/.config/opencode/plugins`，插件分别写入 `state-opencode-*` 和 `state-openchamber-*`；浮球合并显示两边的活动会话。

## 目录

```
plugin/tps-live.js   OpenCode 插件（OpenChamber 共用）
app/common.py        路径、进程检测、互斥
app/overlay.py       Tkinter 浮球 / 面板
app/watcher.py       随 OpenCode / OpenChamber 启停的守护进程
install.ps1          安装、启动项、启动守护进程
uninstall.ps1        卸载
dist/                站点静态文件（index.html、assets、下载包）
tools/make_og.ps1    重新生成站点 OG 图
```

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

或手动删除：

- 启动文件夹中的 `OpenCode TPS.lnk`（旧版为 `OpenChamber TPS.lnk`）
- `%USERPROFILE%\.config\opencode\plugins\tps-live.js`
- `%LOCALAPPDATA%\OpenChamberTps`
- 结束命令行中包含 `OpenChamberTps` 的 `pythonw.exe` 进程

## 隐私

- 不发送网络请求，不读取 API Key
- 插件只订阅本地会话事件，并把当前速度写入 `%LOCALAPPDATA%\OpenChamberTps\state-*.json`
- 悬浮窗只读取这些本地状态文件

## 限制

- 当前安装包只面向 Windows；macOS / Linux 需要手动放置文件并配置启动方式
- 流式速度是估算值，精确值在回合结束后才可用
- 面板最多显示 4 个会话；更多会话只在浮球徽标里显示数量
- 依赖 OpenCode v2 插件事件接口；OpenCode / OpenChamber 大版本更新后可能需要适配
- 非官方工具，不隶属于 OpenCode 或 OpenChamber
