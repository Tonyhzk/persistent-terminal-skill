---
name: persistent-terminal
version: 1.1.0
description: 跨平台持久终端会话管理。当需要在多轮对话中保持同一个终端会话、运行交互式程序、维持环境变量和进程状态时使用。关键词：持久终端、终端会话、交互式终端、persistent terminal、session。
---

# 持久终端会话

跨平台持久终端会话管理，支持在多轮对话中访问同一个终端。

## 可用命令

```bash
# 创建新会话（默认前台附着，用户可实时看到输出）
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py create --name SESSION_NAME

# 创建后台会话（不附着）
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py create --name SESSION_NAME --background

# 附着到已有会话（实时查看输出，Ctrl+C 退出附着）
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py attach --name SESSION_NAME

# 在会话中执行命令
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py exec --name SESSION_NAME --cmd "命令内容"

# 读取会话输出（获取最新输出）
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py read --name SESSION_NAME

# 列出所有活跃会话
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py list

# 关闭会话
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py close --name SESSION_NAME

# 关闭所有会话
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py close-all

# 发送纯文本（不加标记，适用于密码等交互式输入）
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py send --name SESSION_NAME --text "文本内容"

# 从 JSON 配置文件读取文本发送（绕过 bash 特殊字符问题）
python3 %当前SKILL文件父目录%/scripts/persistent_terminal.py send --name SESSION_NAME --config "配置文件路径" --key "键路径"
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `--name` | 会话名称，用于标识不同终端 |
| `--cmd` | 要执行的命令 |
| `--timeout` | exec 等待输出的超时秒数（默认 10） |
| `--lines` | read 读取的行数（默认 50） |
| `--shell` | 指定 shell（默认：macOS/Linux 用 bash，Windows 用 cmd） |
| `--background` | create 时不附着前台，后台静默创建 |
| `--text` | send 时要发送的纯文本 |
| `--config` | send 时从 JSON 配置文件读取文本，传文件路径 |
| `--key` | JSON 键路径，点号分隔，如 `profiles.myserver.password` |

## 使用规范

### 启动前检查残留会话

每次使用此技能前，必须先执行 `list` 检查是否有上次残留的会话：
- 有残留 → 询问用户是否关闭残留会话，还是继续使用
- 无残留 → 正常创建新会话

### 任务结束后清理

当判断用户的终端相关需求已完成时，必须用 AskUserQuestion 询问用户是否关闭会话：
- 用户选择关闭 → 执行 `close` 或 `close-all`
- 用户选择保留 → 不做操作，会话继续在后台运行

### 前台与后台选择

- 默认使用前台模式（`create --name xxx`），会自动弹出系统终端窗口
- 仅当用户明确不需要看到窗口时，使用后台模式（`--background`）

## 使用场景

- 启动开发服务器后，在后续对话中继续与之交互
- 保持 SSH 连接，多次执行远程命令
- 运行需要环境变量持久化的多步骤任务
- 交互式程序（如 Python REPL、数据库客户端）

## 平台支持

| 平台 | 实现方式 |
|------|----------|
| macOS / Linux | tmux（自动安装） |
| Windows | 独立进程执行模式 |

## 注意：Bash 工具特殊字符问题

通过 Bash 工具调用 send 传递含特殊字符（如"!"、"$"、"`"）的文本时，Bash shell 会在传递给 Python 之前解释这些字符，导致内容被篡改。

**受影响场景**：SSH 密码输入、含特殊符号的命令等。

**解决方案**：使用 `--config` + `--key` 从 JSON 文件读取，Python 内部直接读文件，完全绕过 bash 解析。

备用方案：在 Python 中用转义表示（如 `\x21` 代替"!"），避免 bash 解释

## 输出格式

所有命令返回 JSON：

```json
{
  "success": true,
  "session": "会话名称",
  "output": "命令输出内容"
}
```

## 作者

**Tonyhzk** · [GitHub](https://github.com/Tonyhzk) · [项目地址](https://github.com/Tonyhzk/persistent-terminal-skill)
