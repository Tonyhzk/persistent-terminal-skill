<div align="center">

![Persistent Terminal Skill](assets/banner.svg)

</div>

# Persistent Terminal Skill

Claude Code 跨平台持久终端会话管理技能。在多轮对话中保持同一个终端会话，运行交互式程序、维持环境变量和进程状态。

[English](README.md) | **中文** | [更新日志](CHANGELOG_CN.md)

---

## 功能特性

### 核心功能
- **持久会话** - 终端会话跨多轮 Claude Code 对话保持存活
- **跨平台支持** - macOS/Linux（tmux）和 Windows（子进程）
- **会话管理** - 创建、附着、执行、读取、关闭会话
- **前台与后台** - 可选弹出终端窗口或静默后台运行

### 特色功能
- **交互式输入** - 发送原始文本，适用于密码等交互场景
- **特殊字符绕过** - 通过 JSON 配置文件传递文本，避免 bash 转义问题
- **JSON 输出** - 所有命令返回结构化 JSON
- **会话清理** - 列出并关闭残留会话

---

## 系统要求

| 平台 | 要求 |
|------|------|
| macOS | Python 3，tmux（自动安装） |
| Linux | Python 3，tmux（自动安装） |
| Windows | Python 3 |

---

## 安装

### 方式一：克隆到本地

```bash
git clone https://github.com/Tonyhzk/persistent-terminal-skill.git
```

### 方式二：作为 Claude Code Skill 安装

将 `src/persistent-terminal` 目录复制到你的 Claude Code Skills 目录中即可使用。

### 配置共享（可选）

如果你有多个项目需要共享 `.claude` 配置，可以使用符号链接工具：

```bash
python3 setup_claude_dir.py
```

该工具支持交互式菜单和命令行模式：

```bash
python3 setup_claude_dir.py link      # 创建符号链接
python3 setup_claude_dir.py unlink    # 移除符号链接
python3 setup_claude_dir.py status    # 查看当前状态
```

---

## 使用方式

安装后，在 Claude Code 中通过 `/tool-persistent-terminal` 调用，或在对话中提及"持久终端"、"终端会话"等关键词自动触发。

### 可用命令

| 命令 | 说明 |
|------|------|
| `create` | 创建新终端会话 |
| `attach` | 附着到已有会话（实时查看输出） |
| `exec` | 在会话中执行命令 |
| `read` | 读取会话最近输出 |
| `send` | 发送纯文本（密码、交互式输入） |
| `list` | 列出所有活跃会话 |
| `close` | 关闭指定会话 |
| `close-all` | 关闭所有会话 |

### 参数说明

| 参数 | 说明 |
|------|------|
| `--name` | 会话名称标识 |
| `--cmd` | 要执行的命令 |
| `--timeout` | exec 等待超时秒数（默认 10） |
| `--lines` | read 读取行数（默认 30） |
| `--max-chars` | read 最大字符数（默认 2000，0 为不限制） |
| `--output` | read 输出到文件（不输出到 stdout，节省上下文） |
| `--shell` | 指定 shell（默认：macOS/Linux 用 bash，Windows 用 cmd） |
| `--background` | 后台创建，不弹出窗口 |
| `--text` | 发送的纯文本内容 |
| `--config` | JSON 配置文件路径 |
| `--key` | JSON 键路径（点号分隔） |

---

## 使用场景

- 启动开发服务器后，在后续对话中继续交互
- 保持 SSH 连接，多次执行远程命令
- 运行需要环境变量持久化的多步骤任务
- 交互式程序（Python REPL、数据库客户端等）

---

## 项目结构

```
persistent-terminal-skill/
├── src/persistent-terminal/   # 技能源码
│   ├── SKILL.md               # 技能定义文件
│   └── scripts/               # 核心脚本
├── 1_Script/                  # 实用工具脚本
├── setup_claude_dir.py        # 符号链接管理工具
├── README.md                  # 英文文档
└── README_CN.md               # 中文文档
```

---

## 许可证

[Apache License 2.0](LICENSE)

## 作者

**Tonyhzk**

- GitHub: [@Tonyhzk](https://github.com/Tonyhzk)
- 项目地址: [persistent-terminal-skill](https://github.com/Tonyhzk/persistent-terminal-skill)