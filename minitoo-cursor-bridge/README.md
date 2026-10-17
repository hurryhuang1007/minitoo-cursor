# Cursor → MiniToo bridge

独立消费端：只读取 `~/.minitoo/cursor-state.json`，按状态发送
`../sprites/{status}/f1–f4-black.png` 角色动画到 MiniToo。
不改 Cursor、不走 MCP、不读提示词或对话正文。

## 状态 → 动画

| Hook / 显示状态 | 精灵目录 | 动作 |
| --- | --- | --- |
| `idle` | `sprites/idle` | 招手 |
| `running` | `sprites/running` | 干饭 |
| `completed` | `sprites/completed` | 举碗庆祝（约 12 秒后回 idle） |
| `aborted` | `sprites/aborted` | 歪头 |
| `error` | `sprites/error` | 惊讶 |
| 过期 `running` | 显示为 idle | `STALE` |

## 推荐：开机自启（不用手管）

Supervisor 会：
- **始终**运行 bridge（监听 Cursor 状态）
- **仅当** MiniToo 蓝牙已连接时启动 daemon；断开则停掉 daemon

```zsh
cd ~/Desktop/workspace/minitoo-cursor
chmod +x supervisor/install-autostart.sh supervisor/uninstall-autostart.sh
./supervisor/install-autostart.sh          # 默认 MAC B1:21:81:91:DE:0A
# 或
./supervisor/install-autostart.sh AA:BB:CC:DD:EE:FF
```

日志：`~/.minitoo/supervisor.log`、`bridge.log`、`daemon.log`  
卸载：`./supervisor/uninstall-autostart.sh`

## 手动启动（调试用）

```zsh
# 终端 1
./divoom-minitoo-osx/tools/divoom-daemon B1:21:81:91:DE:0A 1 40583

# 终端 2
./divoom-minitoo-osx/.venv/bin/python \
  ./minitoo-cursor-bridge/cursor_minitoo_bridge.py \
  --sender ./divoom-minitoo-osx/tools/divoom_send.py
```

离线只建包、不连设备：

```zsh
./divoom-minitoo-osx/.venv/bin/python \
  ./minitoo-cursor-bridge/cursor_minitoo_bridge.py \
  --sender ./divoom-minitoo-osx/tools/divoom_send.py \
  --once --dry-run
```
