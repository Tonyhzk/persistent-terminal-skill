#!/usr/bin/env python3
"""跨平台持久终端会话管理器"""

# === 依赖加载 ===
import sys
from pathlib import Path

_p = Path(__file__).resolve().parent
while _p != _p.parent:
    if _p.name == "skills" and (_p / ".scripts" / "lib" / "libloader.py").exists():
        sys.path.insert(0, str(_p / ".scripts" / "lib"))
        from libloader import setup
        setup()
        break
    _p = _p.parent
# === 依赖加载结束 ===

import argparse
import json
import platform
import time
import logging

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent


def _find_claude_dir() -> Path:
    d = Path(__file__).resolve().parent
    while d != d.parent:
        if (d / ".claude").is_dir():
            return d / ".claude"
        d = d.parent
    raise FileNotFoundError("找不到 .claude 目录")


def setup_logger(script_name: str) -> logging.Logger:
    log_dir = Path.cwd() / ".temp" / ".log"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / f"{script_name}.log"),
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        encoding="utf-8",
    )
    return logging.getLogger(script_name)


logger = setup_logger("persistent-terminal")

# === 全局会话存储 ===
# 注意：由于每次 Bash 调用是独立进程，会话无法在内存中跨调用保持。
# 因此使用文件系统持久化会话信息，并通过 tmux/screen 或子进程管道实现持久化。

SESSION_DIR = Path.cwd() / ".temp" / "terminal-sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

IS_WINDOWS = platform.system() == "Windows"

def _get_session_file(name: str) -> Path:
    return SESSION_DIR / f"{name}.json"


def _save_session_info(name: str, pid: int, shell: str):
    info = {"name": name, "pid": pid, "shell": shell, "created_at": time.time()}
    _get_session_file(name).write_text(json.dumps(info), encoding="utf-8")


def _load_session_info(name: str) -> dict | None:
    f = _get_session_file(name)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return None


def _remove_session_info(name: str):
    f = _get_session_file(name)
    if f.exists():
        f.unlink()


def _result(success: bool, **kwargs) -> str:
    data = {"success": success, **kwargs}
    return json.dumps(data, ensure_ascii=False, indent=2)


def _check_tmux() -> bool:
    """检查 tmux 是否可用，不可用时自动安装"""
    import subprocess, shutil

    if shutil.which("tmux"):
        return True

    if IS_WINDOWS:
        return False

    # 自动安装 tmux
    logger.info("tmux 未安装，尝试自动安装...")
    installers = [
        (["brew", "install", "tmux"], "brew"),
        (["sudo", "apt-get", "install", "-y", "tmux"], "apt"),
        (["sudo", "yum", "install", "-y", "tmux"], "yum"),
    ]
    for cmd, name in installers:
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0 and shutil.which("tmux"):
                logger.info(f"tmux 通过 {name} 安装成功")
                return True
            logger.warning(f"{name} 安装失败: {r.stderr.strip()}")
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"{name} 安装异常: {e}")
    return False


# === tmux 后端（macOS/Linux 首选） ===

class TmuxBackend:
    """使用 tmux 实现持久终端会话"""

    @staticmethod
    def create(name: str, shell: str | None = None) -> str:
        import subprocess
        if not _check_tmux():
            return _result(False, error="tmux 自动安装失败，请手动安装: brew install tmux (macOS) 或 apt install tmux (Linux)")

        # 检查会话是否已存在
        r = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True)
        if r.returncode == 0:
            return _result(False, error=f"会话 '{name}' 已存在")

        shell_cmd = shell or "/bin/bash"
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-x", "200", "-y", "50", shell_cmd],
            capture_output=True, check=True,
        )
        # 获取 tmux server pid
        r2 = subprocess.run(["tmux", "display-message", "-t", name, "-p", "#{pid}"], capture_output=True, text=True)
        pid = int(r2.stdout.strip()) if r2.stdout.strip().isdigit() else 0
        _save_session_info(name, pid, shell_cmd)
        logger.info(f"创建会话: {name}, shell={shell_cmd}")
        return _result(True, session=name, message=f"会话 '{name}' 已创建")

    @staticmethod
    def exec_cmd(name: str, cmd: str, timeout: int = 10) -> str:
        import subprocess

        # 检查会话是否存在
        r = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True)
        if r.returncode != 0:
            return _result(False, error=f"会话 '{name}' 不存在")

        # 用唯一标记包裹命令，方便提取输出
        marker = f"__CMD_{int(time.time() * 1000)}__"
        start_marker = f"echo '{marker}_START'"
        end_marker = f"echo '{marker}_END'"

        # 发送命令
        subprocess.run(["tmux", "send-keys", "-t", name, start_marker, "Enter"], capture_output=True)
        time.sleep(0.1)
        subprocess.run(["tmux", "send-keys", "-t", name, cmd, "Enter"], capture_output=True)
        subprocess.run(["tmux", "send-keys", "-t", name, end_marker, "Enter"], capture_output=True)

        # 等待输出完成
        output = ""
        for _ in range(timeout * 10):
            time.sleep(0.1)
            r = subprocess.run(
                ["tmux", "capture-pane", "-t", name, "-p", "-S", "-1000"],
                capture_output=True, text=True,
            )
            captured = r.stdout
            if f"{marker}_END" in captured:
                # 提取 START 和 END 之间的内容
                lines = captured.split("\n")
                collecting = False
                result_lines = []
                for line in lines:
                    if f"{marker}_START" in line:
                        collecting = True
                        continue
                    if f"{marker}_END" in line:
                        collecting = False
                        continue
                    if collecting:
                        result_lines.append(line)
                # 去掉第一行（命令本身的回显）和最后的空行
                if result_lines and cmd.strip() in result_lines[0]:
                    result_lines = result_lines[1:]
                output = "\n".join(result_lines).rstrip()
                break
        else:
            # 超时，只返回简短提示，不返回历史内容
            return _result(True, session=name, output="", warning="命令执行超时，请稍后用 read 查看输出")

        logger.info(f"执行命令: session={name}, cmd={cmd}")
        return _result(True, session=name, output=output)

    @staticmethod
    def send(name: str, text: str) -> str:
        """纯文本发送，不加标记，适用于密码等交互式输入"""
        import subprocess
        r = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True)
        if r.returncode != 0:
            return _result(False, error=f"会话 '{name}' 不存在")
        subprocess.run(["tmux", "send-keys", "-t", name, "-l", text], capture_output=True)
        subprocess.run(["tmux", "send-keys", "-t", name, "Enter"], capture_output=True)
        logger.info(f"发送文本: session={name}, len={len(text)}")
        return _result(True, session=name, message="文本已发送")

    @staticmethod
    def read(name: str, lines: int = 30, max_chars: int = 2000, output_file: str = "") -> str:
        import subprocess
        r = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True)
        if r.returncode != 0:
            return _result(False, error=f"会话 '{name}' 不存在")

        r = subprocess.run(
            ["tmux", "capture-pane", "-t", name, "-p", "-S", f"-{lines}"],
            capture_output=True, text=True,
        )
        output = r.stdout.rstrip()
        # 截断过长输出
        if max_chars > 0 and len(output) > max_chars:
            output = output[-max_chars:] + "\n... (输出已截断)"

        # 如果指定了输出文件，写入文件并返回简短结果
        if output_file:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            return _result(True, session=name, output_file=output_file, lines_count=len(output.split("\n")))

        return _result(True, session=name, output=output)

    @staticmethod
    def list_sessions() -> str:
        import subprocess
        if not _check_tmux():
            return _result(True, sessions=[])

        r = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}|#{session_created}|#{session_attached}"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return _result(True, sessions=[])

        sessions = []
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            sessions.append({
                "name": parts[0],
                "created": int(parts[1]) if len(parts) > 1 else 0,
                "attached": parts[2] == "1" if len(parts) > 2 else False,
            })
        return _result(True, sessions=sessions)

    @staticmethod
    def close(name: str) -> str:
        import subprocess
        r = subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True)
        _remove_session_info(name)
        if r.returncode == 0:
            logger.info(f"关闭会话: {name}")
            return _result(True, session=name, message=f"会话 '{name}' 已关闭")
        return _result(False, error=f"关闭失败: {r.stderr.strip()}")

    @staticmethod
    def close_all() -> str:
        import subprocess
        subprocess.run(["tmux", "kill-server"], capture_output=True)
        # 清理所有会话文件
        for f in SESSION_DIR.glob("*.json"):
            f.unlink()
        logger.info("关闭所有会话")
        return _result(True, message="所有会话已关闭")



# === subprocess 后端（纯标准库，跨平台回退） ===
# 使用 FIFO 命名管道（Unix）或独立进程执行（Windows）实现持久化

class SubprocessBackend:
    """使用 subprocess + FIFO 命名管道实现持久终端"""

    @staticmethod
    def create(name: str, shell: str | None = None) -> str:
        import subprocess as sp
        import os

        info = _load_session_info(name)
        if info:
            try:
                os.kill(info["pid"], 0)
                return _result(False, error=f"会话 '{name}' 已存在 (PID: {info['pid']})")
            except (OSError, ProcessLookupError):
                _remove_session_info(name)

        pipe_dir = SESSION_DIR / name
        pipe_dir.mkdir(parents=True, exist_ok=True)
        output_file = pipe_dir / "output.log"
        output_file.write_text("", encoding="utf-8")

        if IS_WINDOWS:
            # Windows: 无 FIFO，使用独立进程模式
            shell_cmd = shell or "cmd.exe"
            _save_session_info(name, 0, shell_cmd)
            logger.info(f"创建会话(windows): {name}")
            return _result(True, session=name, message=f"会话 '{name}' 已创建（独立进程模式）", backend="subprocess-windows")

        # Unix: 使用 FIFO 命名管道
        shell_cmd = shell or "/bin/bash"
        fifo_path = pipe_dir / "stdin.fifo"

        # 清理旧 FIFO
        if fifo_path.exists():
            fifo_path.unlink()

        os.mkfifo(str(fifo_path))

        # 启动守护脚本：从 FIFO 读取命令，通过 shell 执行，输出写入 log
        daemon_script = f"""
import os, subprocess, sys, time
fifo = "{fifo_path}"
output = "{output_file}"
shell = "{shell_cmd}"
pid_file = "{pipe_dir / 'daemon.pid'}"

# 写入守护进程 PID
with open(pid_file, 'w') as f:
    f.write(str(os.getpid()))

# 启动 shell 进程
with open(output, 'a') as out_f:
    proc = subprocess.Popen(
        [shell],
        stdin=subprocess.PIPE,
        stdout=out_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # 持续从 FIFO 读取命令并写入 shell stdin
    while True:
        try:
            with open(fifo, 'r') as fifo_f:
                for line in fifo_f:
                    if line.strip() == '__EXIT_SESSION__':
                        proc.stdin.close()
                        proc.wait()
                        sys.exit(0)
                    try:
                        proc.stdin.write(line.encode())
                        proc.stdin.flush()
                    except (BrokenPipeError, OSError):
                        sys.exit(1)
        except (OSError, IOError):
            time.sleep(0.1)
"""
        # 启动守护进程
        daemon_proc = sp.Popen(
            [sys.executable, "-c", daemon_script],
            start_new_session=True,
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )

        # 等待守护进程写入 PID 文件
        time.sleep(0.5)
        pid_file = pipe_dir / "daemon.pid"
        if pid_file.exists():
            daemon_pid = int(pid_file.read_text().strip())
        else:
            daemon_pid = daemon_proc.pid

        _save_session_info(name, daemon_pid, shell_cmd)
        logger.info(f"创建会话(fifo): {name}, PID={daemon_pid}")
        return _result(True, session=name, message=f"会话 '{name}' 已创建 (PID: {daemon_pid})", backend="subprocess-fifo")

    @staticmethod
    def exec_cmd(name: str, cmd: str, timeout: int = 10) -> str:
        import os

        info = _load_session_info(name)
        if not info:
            return _result(False, error=f"会话 '{name}' 不存在")

        pipe_dir = SESSION_DIR / name
        output_file = pipe_dir / "output.log"
        fifo_path = pipe_dir / "stdin.fifo"

        if not output_file.exists():
            return _result(False, error=f"会话 '{name}' 的输出文件不存在")

        # 检查进程是否存活
        pid = info["pid"]
        if pid > 0:
            try:
                os.kill(pid, 0)
            except (OSError, ProcessLookupError):
                # 进程已死，回退到独立进程执行
                return _exec_via_new_process(name, cmd, timeout, output_file, output_file.stat().st_size)

        before_size = output_file.stat().st_size

        if IS_WINDOWS or not fifo_path.exists():
            return _exec_via_new_process(name, cmd, timeout, output_file, before_size)

        # 通过 FIFO 发送命令
        try:
            with open(fifo_path, "w") as f:
                f.write(cmd + "\n")
        except (OSError, IOError) as e:
            return _exec_via_new_process(name, cmd, timeout, output_file, before_size)

        # 等待输出
        for _ in range(timeout * 10):
            time.sleep(0.1)
            current_size = output_file.stat().st_size
            if current_size > before_size:
                time.sleep(0.3)
                # 再检查一次，确保输出稳定
                final_size = output_file.stat().st_size
                if final_size == current_size:
                    break

        new_output = output_file.read_text(encoding="utf-8")[before_size:].rstrip()
        logger.info(f"执行命令: session={name}, cmd={cmd}")
        return _result(True, session=name, output=new_output)

    @staticmethod
    def send(name: str, text: str) -> str:
        """纯文本发送，通过 FIFO 写入，适用于密码等交互式输入"""
        pipe_dir = SESSION_DIR / name
        fifo_path = pipe_dir / "stdin.fifo"
        if not fifo_path.exists():
            return _result(False, error=f"会话 '{name}' 不存在或无 FIFO")
        try:
            with open(fifo_path, "w") as f:
                f.write(text + "\n")
            logger.info(f"发送文本: session={name}, len={len(text)}")
            return _result(True, session=name, message="文本已发送")
        except (OSError, IOError) as e:
            return _result(False, error=str(e))

    @staticmethod
    def read(name: str, lines: int = 50, output_file: str = "") -> str:
        pipe_dir = SESSION_DIR / name
        log_file = pipe_dir / "output.log"
        if not log_file.exists():
            return _result(False, error=f"会话 '{name}' 不存在")

        content = log_file.read_text(encoding="utf-8")
        last_lines = "\n".join(content.split("\n")[-lines:])
        output = last_lines.rstrip()

        # 如果指定了输出文件，写入文件并返回简短结果
        if output_file:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            return _result(True, session=name, output_file=output_file, lines_count=len(output.split("\n")))

        return _result(True, session=name, output=output)

    @staticmethod
    def list_sessions() -> str:
        import os
        sessions = []
        for f in SESSION_DIR.glob("*.json"):
            info = json.loads(f.read_text(encoding="utf-8"))
            alive = False
            if info.get("pid", 0) > 0:
                try:
                    os.kill(info["pid"], 0)
                    alive = True
                except (OSError, ProcessLookupError):
                    pass
            info["alive"] = alive
            sessions.append(info)
        return _result(True, sessions=sessions)

    @staticmethod
    def close(name: str) -> str:
        import os, signal, shutil

        info = _load_session_info(name)
        if not info:
            return _result(False, error=f"会话 '{name}' 不存在")

        pipe_dir = SESSION_DIR / name
        fifo_path = pipe_dir / "stdin.fifo"

        # 发送退出信号
        if not IS_WINDOWS and fifo_path.exists():
            try:
                with open(fifo_path, "w") as f:
                    f.write("__EXIT_SESSION__\n")
                time.sleep(0.3)
            except (OSError, IOError):
                pass

        # 强制终止进程
        if info.get("pid", 0) > 0:
            try:
                os.kill(info["pid"], signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

        _remove_session_info(name)
        if pipe_dir.exists():
            shutil.rmtree(pipe_dir, ignore_errors=True)
        logger.info(f"关闭会话: {name}")
        return _result(True, session=name, message=f"会话 '{name}' 已关闭")

    @staticmethod
    def close_all() -> str:
        import os, signal, shutil

        for f in SESSION_DIR.glob("*.json"):
            info = json.loads(f.read_text(encoding="utf-8"))
            if info.get("pid", 0) > 0:
                try:
                    os.kill(info["pid"], signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
        for d in SESSION_DIR.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
            elif d.is_file():
                d.unlink()
        logger.info("关闭所有会话")
        return _result(True, message="所有会话已关闭")


def _exec_via_new_process(name: str, cmd: str, timeout: int, output_file: Path, before_size: int) -> str:
    """回退方案：通过新进程执行命令并追加输出"""
    import subprocess as sp

    shell_cmd = "cmd.exe" if IS_WINDOWS else "/bin/bash"
    try:
        r = sp.run(
            [shell_cmd, "-c", cmd] if not IS_WINDOWS else [shell_cmd, "/c", cmd],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(Path.home()),
        )
        output = r.stdout + r.stderr
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"$ {cmd}\n{output}\n")
        return _result(True, session=name, output=output.rstrip(), note="通过独立进程执行")
    except sp.TimeoutExpired:
        return _result(True, session=name, output="", warning="命令执行超时")
    except Exception as e:
        return _result(False, error=str(e))


# === 后端选择 ===

def _get_backend():
    """自动选择最佳后端：tmux > subprocess"""
    if not IS_WINDOWS and _check_tmux():
        return TmuxBackend
    return SubprocessBackend


# === attach 功能 ===

def _open_terminal_window(name: str) -> bool:
    """在系统终端窗口中打开 tmux 会话，返回是否成功"""
    import subprocess

    system = platform.system()
    if system == "Darwin":
        # macOS: 用 Terminal.app 打开
        script = f'''
        tell application "Terminal"
            do script "tmux attach-session -t {name}"
            activate
        end tell
        '''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    elif system == "Linux":
        # Linux: 尝试常见终端模拟器
        terminals = [
            ["gnome-terminal", "--", "tmux", "attach-session", "-t", name],
            ["xterm", "-e", f"tmux attach-session -t {name}"],
            ["konsole", "-e", f"tmux attach-session -t {name}"],
        ]
        import shutil
        for cmd in terminals:
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, start_new_session=True)
                    return True
                except OSError:
                    continue
    return False


def _attach_session(name: str):
    """附着到会话：优先弹出系统终端窗口，回退到当前终端轮询"""
    backend = _get_backend()

    # tmux 后端
    if backend == TmuxBackend:
        import subprocess
        r = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True)
        if r.returncode != 0:
            print(_result(False, error=f"会话 '{name}' 不存在"))
            return

        # 优先弹出系统终端窗口
        if _open_terminal_window(name):
            print(_result(True, session=name, message=f"已在系统终端窗口中打开会话 '{name}'"))
            return

        # 回退：当前终端轮询
        print(f"[已附着到会话 '{name}'，Ctrl+C 退出]")
        last_content = ""
        try:
            while True:
                r = subprocess.run(
                    ["tmux", "capture-pane", "-t", name, "-p", "-S", "-100"],
                    capture_output=True, text=True,
                )
                content = r.stdout.rstrip()
                if content != last_content:
                    if last_content and content.startswith(last_content):
                        new_part = content[len(last_content):]
                        if new_part:
                            print(new_part, end="", flush=True)
                    else:
                        print(content, flush=True)
                    last_content = content
                time.sleep(0.3)
        except KeyboardInterrupt:
            print(f"\n[已从会话 '{name}' 分离]")
        return

    # subprocess 后端：tail -f output.log
    pipe_dir = SESSION_DIR / name
    output_file = pipe_dir / "output.log"
    if not output_file.exists():
        print(_result(False, error=f"会话 '{name}' 不存在"))
        return

    print(f"[已附着到会话 '{name}'，Ctrl+C 退出]")
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()
            if content:
                print(content, end="", flush=True)
            while True:
                line = f.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\n[已从会话 '{name}' 分离]")


# === CLI 入口 ===

def parse_args():
    parser = argparse.ArgumentParser(description="跨平台持久终端会话管理器")
    subparsers = parser.add_subparsers(dest="action", help="可用命令")

    # create
    p_create = subparsers.add_parser("create", help="创建新会话")
    p_create.add_argument("--name", required=True, help="会话名称")
    p_create.add_argument("--shell", default=None, help="指定 shell")
    p_create.add_argument("--background", action="store_true", help="后台创建，不附着前台")

    # attach
    p_attach = subparsers.add_parser("attach", help="附着到会话（实时查看输出）")
    p_attach.add_argument("--name", required=True, help="会话名称")

    # exec
    p_exec = subparsers.add_parser("exec", help="在会话中执行命令")
    p_exec.add_argument("--name", required=True, help="会话名称")
    p_exec.add_argument("--cmd", required=True, help="要执行的命令")
    p_exec.add_argument("--timeout", type=int, default=10, help="超时秒数")

    # read
    p_read = subparsers.add_parser("read", help="读取会话输出")
    p_read.add_argument("--name", required=True, help="会话名称")
    p_read.add_argument("--lines", type=int, default=30, help="读取行数（默认30）")
    p_read.add_argument("--max-chars", type=int, default=2000, help="最大字符数（默认2000，0表示不限制）")
    p_read.add_argument("--output", default="", help="输出到文件（不输出到 stdout，节省上下文）")

    # list
    subparsers.add_parser("list", help="列出所有会话")

    # close
    p_close = subparsers.add_parser("close", help="关闭会话")
    p_close.add_argument("--name", required=True, help="会话名称")

    # close-all
    subparsers.add_parser("close-all", help="关闭所有会话")

    # send
    p_send = subparsers.add_parser("send", help="发送纯文本（不加标记，适用于密码等交互式输入）")
    p_send.add_argument("--name", required=True, help="会话名称")
    p_send.add_argument("--text", default=None, help="要发送的文本")
    p_send.add_argument("--config", default=None, help="从 JSON 配置文件读取文本，格式：文件路径")
    p_send.add_argument("--key", default=None, help="JSON 键路径，用点号分隔，如 profiles.myserver.password")

    return parser.parse_args()


def main():
    args = parse_args()
    if not args.action:
        print(_result(False, error="请指定命令: create, attach, exec, read, list, close, close-all"))
        return

    backend = _get_backend()
    backend_name = backend.__name__

    if args.action == "create":
        result_str = backend.create(args.name, args.shell)
        print(result_str)
        # 默认前台附着，除非指定 --background
        result_data = json.loads(result_str)
        if result_data.get("success") and not args.background:
            _attach_session(args.name)
    elif args.action == "attach":
        _attach_session(args.name)
    elif args.action == "exec":
        print(backend.exec_cmd(args.name, args.cmd, args.timeout))
    elif args.action == "read":
        max_chars = getattr(args, 'max_chars', 2000)
        output_file = getattr(args, 'output', '')
        print(backend.read(args.name, args.lines, max_chars, output_file))
    elif args.action == "list":
        result = json.loads(backend.list_sessions())
        result["backend"] = backend_name
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "close":
        print(backend.close(args.name))
    elif args.action == "close-all":
        print(backend.close_all())
    elif args.action == "send":
        # 确定要发送的文本：--config + --key 优先，其次 --text
        text = args.text
        if args.config and args.key:
            try:
                with open(args.config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k in args.key.split("."):
                    data = data[k]
                text = str(data)
            except (FileNotFoundError, KeyError, TypeError) as e:
                print(_result(False, error=f"读取配置失败: {e}"))
                return
        if text is None:
            print(_result(False, error="需要 --text 或 --config + --key 参数"))
            return
        print(backend.send(args.name, text))


if __name__ == "__main__":
    main()
