# MiniToo Cursor

> 让 Cursor Agent 的工作状态，跑到 Divoom MiniToo 桌面音箱的像素屏上。
> 使用其他 Agent，或者希望换成不同的交互形象？又或者不会安装/懒得操作？
> 把本项目交给你的 AI Agent 即可——相信它能理解并妥善处理。

![idle preview](sprites/idle/loop.gif)

## 这是什么

**MiniToo Cursor** 是一套本地、轻量的 Cursor Agent 状态可视化方案：

1. **Cursor Hooks** 把 Agent 生命周期写成 `~/.minitoo/cursor-state.json`（不读对话正文、不调 AI、不连网）
2. **Bridge** 轮询该文件，按状态切换角色动画
3. **Divoom Daemon** 通过蓝牙 RFCOMM 把画面送到 MiniToo
4. **Supervisor + launchd** 开机自启：Bridge 常驻；仅在 MiniToo 已连接时启动 Daemon

整条链路都在本机完成，不依赖 MCP，也不改 Cursor 模型或业务项目代码。

## 状态一览

| 状态        | 动画                 |
| ----------- | -------------------- |
| `idle`      | 招手待机             |
| `running`   | 干饭（Agent 忙碌中） |
| `completed` | 举碗庆祝             |
| `aborted`   | 歪头                 |
| `error`     | 惊讶                 |

角色是 DeepSeek 鲸鱼娘：蓝色渐层发鲸系女仆 Q 版像素形象；背景为日式春日夕阳 + 错落樱花树 + 飘落花瓣（循环 4 帧）。

## 仓库结构

```
.
├── minitoo-cursor-bridge/   # 状态消费端（轮询 Hook 状态 → 发动画）
├── divoom-minitoo-osx/      # MiniToo RFCOMM daemon / 发包工具（基于上游改造）
├── sprites/                 # 各状态 128×128 精灵帧与 GIF
├── supervisor/              # 开机自启：蓝牙监视 + 拉起 bridge/daemon
└── README.md
```

上游蓝牙协议与 daemon 参考：[alvinunreal/divoom-minitoo-osx](https://github.com/alvinunreal/divoom-minitoo-osx)（本仓库内已 vendored，并含 macOS channel-open 小补丁）。

## 环境要求

- macOS（蓝牙经典 RFCOMM）
- 已配对的 Divoom MiniToo
- Python 3（bridge 使用项目内 `.venv`，见下方安装）
- Cursor（启用用户级 Hooks）

## 快速开始

### 1. 安装 Python 依赖（首次）

```zsh
cd divoom-minitoo-osx
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install -r ../minitoo-cursor-bridge/requirements.txt
# Pillow / zstandard 等，见 requirements
```

若 daemon 二进制缺失，可按 `divoom-minitoo-osx/README.md` 用 `swiftc` 重新编译 `tools/divoom-daemon`。

### 2. 安装 Cursor Hooks（状态写入）

```zsh
mkdir -p ~/.cursor/hooks
cp cursor-hooks/minitoo-cursor-state.py ~/.cursor/hooks/
chmod +x ~/.cursor/hooks/minitoo-cursor-state.py
cp cursor-hooks/hooks.json.example ~/.cursor/hooks.json
```

若已有 `~/.cursor/hooks.json`，请手动合并 `cursor-hooks/hooks.json.example` 中的事件，勿直接覆盖。

Hook 只写最少字段到 `~/.minitoo/cursor-state.json`：`status` / `event` / `updated_at` / 可选 `conversation_id`、`generation_id`。

### 3. 开机自启（推荐）

把仓库里的 MAC 换成你的 MiniToo 地址：

```zsh
chmod +x supervisor/install-autostart.sh supervisor/uninstall-autostart.sh
./supervisor/install-autostart.sh B1:21:81:91:DE:0A
```

之后一般不用再管：

- **Bridge** 始终监听 Cursor 状态；Daemon 刚就绪时会强制推送当前画面（默认 idle），避免设备停在开机屏
- **Daemon** 仅在 MiniToo 蓝牙已连接时启动；断开后会停掉
- 日志：`~/.minitoo/supervisor.log`、`bridge.log`、`daemon.log`

卸载：

```zsh
./supervisor/uninstall-autostart.sh
```

### 4. 手动调试

```zsh
# 终端 1
./divoom-minitoo-osx/tools/divoom-daemon B1:21:81:91:DE:0A 1 40583

# 终端 2
./divoom-minitoo-osx/.venv/bin/python \
  ./minitoo-cursor-bridge/cursor_minitoo_bridge.py \
  --sender ./divoom-minitoo-osx/tools/divoom_send.py
```

离线只建包：

```zsh
./divoom-minitoo-osx/.venv/bin/python \
  ./minitoo-cursor-bridge/cursor_minitoo_bridge.py \
  --sender ./divoom-minitoo-osx/tools/divoom_send.py \
  --once --dry-run
```

## 设计原则

- **不影响 Agent**：Hook 只做轻量 JSON 解析与原子写文件
- **不碰隐私**：不落盘提示词、代码、对话正文
- **不常驻多余 AI/网络进程**：蓝牙只在 Daemon 里
- **设备可缺席**：Bridge 在 Daemon 未就绪时只重试报错，不崩溃

## License / 致谢

- MiniToo 蓝牙发送栈致谢上游 [divoom-minitoo-osx](https://github.com/alvinunreal/divoom-minitoo-osx)
- 角色与动画素材为本项目定制
- Cursor Hooks 文档：https://cursor.com/docs/hooks

---

_「Cursor 但 DeepSeek」233_
