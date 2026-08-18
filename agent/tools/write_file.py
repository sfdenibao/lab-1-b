"""write_file 工具 —— 让 agent 把内容写到磁盘（写脚本 / 存报告 / 落实验产物）。"""
from __future__ import annotations

import os

WRITE_FILE_TOOL: dict = {
    "name": "write_file",
    "description": "Write text content to a local file (creating parent dirs). Returns a confirmation or 'Error: '.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Destination path."},
            "content": {"type": "string", "description": "Text to write."},
        },
        "required": ["path", "content"],
    },
}


def write_file(path: str, content: str) -> str:
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {path}"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"
