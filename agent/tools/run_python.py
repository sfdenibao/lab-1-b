"""run_python 工具 —— agent 自己写的代码，在本机子进程里执行。

⚠️ 安全：执行 LLM 生成的代码有风险。这里的最小防护 = 子进程 + 超时 + 工作目录限定。
真实生产请上沙箱（容器 / Vercel Sandbox 之类）。出错返回 'Error: '。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

RUN_PYTHON_TOOL: dict = {
    "name": "run_python",
    "description": (
        "Execute a snippet of Python code on this machine and return its output. "
        "Use this to compute things, analyze files, or test ideas. Returns combined "
        "returncode + stdout + stderr. On timeout/error returns 'Error: ...'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source to run."},
            "timeout": {"type": "integer", "description": "Seconds before kill (default 30)."},
        },
        "required": ["code"],
    },
}


def run_python(code: str, timeout: int = 30, workdir: str = ".") -> str:
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", dir=workdir, delete=False) as f:
            f.write(code)
            path = f.name
        proc = subprocess.run(
            [sys.executable, path],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (
            f"returncode={proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout[-4000:]}\n"
            f"--- stderr ---\n{proc.stderr[-2000:]}"
        )
    except subprocess.TimeoutExpired:
        return f"Error: code timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
