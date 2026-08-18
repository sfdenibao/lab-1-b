"""run_shell 工具 —— 受限 shell：白名单首命令 + 禁危险 token + 超时。

climax 需要 git clone / pip install / python 跑 quickstart，所以要这个工具——
但执行任意 shell 危险，故只放行白名单、且无 shell=True（metachar 当字面参数）。
"""
from __future__ import annotations

import shlex
import subprocess

ALLOWED = ("git", "pip", "pip3", "python", "python3", "ls", "cat", "mkdir", "echo", "pwd", "head", "tail", "wc")
DANGER = ("rm", "sudo", "chmod", "chown", "mv", ">", ">>", "|", ";", "&&", "||", "`", "$(")

RUN_SHELL_TOOL: dict = {
    "name": "run_shell",
    "description": (
        "Run a whitelisted shell command (git/pip/python/ls/...). Use to clone repos, "
        "install deps, run quickstarts. Refuses anything outside the whitelist or with "
        "dangerous tokens. Returns returncode+stdout+stderr or 'Error: '."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "The command line, e.g. 'git clone https://...'."},
            "timeout": {"type": "integer", "description": "Seconds before kill (default 180)."},
        },
        "required": ["cmd"],
    },
}


def run_shell(cmd: str, timeout: int = 180, workdir: str = ".") -> str:
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return f"Error: cannot parse command: {e}"
    if not parts:
        return "Error: empty command"
    if parts[0] not in ALLOWED:
        return f"Error: command {parts[0]!r} not allowed. Allowed: {', '.join(ALLOWED)}"
    if any(tok in DANGER for tok in parts) or any(d in cmd for d in (";", "|", "&&", "`", "$(")):
        return "Error: refused (dangerous token / shell metacharacter)"
    try:
        proc = subprocess.run(parts, cwd=workdir, capture_output=True, text=True, timeout=timeout)
        return (
            f"returncode={proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout[-4000:]}\n"
            f"--- stderr ---\n{proc.stderr[-2000:]}"
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"
