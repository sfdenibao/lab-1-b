"""list_files 工具 —— 列出本地目录里的文件。

和 read_pdf 一样遵守全 lab 的工具约定：出错返回以 'Error: ' 开头的字符串，**不抛异常**。
这个工具是为「工具路由」演示加的：它和 read_pdf 用途明显不同
（一个「看目录里有什么」，一个「读某个 PDF 的内容」），
所以模型必须根据**问题**自己判断该挑哪一个。
"""
from __future__ import annotations

import os

LIST_FILES_TOOL: dict = {
    "name": "list_files",
    "description": (
        "List the files in a local directory. "
        "Use this when the user wants to know WHICH files exist in a folder "
        "(not the contents of a specific file). "
        "On failure returns a string starting with 'Error: '."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Local directory path to list, e.g. 'data'.",
            },
        },
        "required": ["directory"],
    },
}


def list_files(directory: str) -> str:
    """列出目录下的文件名 + 字节大小（不递归）。"""
    try:
        entries = sorted(os.listdir(directory))
    except Exception as e:  # noqa: BLE001
        return f"Error: cannot list {directory!r}: {type(e).__name__}: {e}"

    rows = []
    for name in entries:
        full = os.path.join(directory, name)
        kind = "dir " if os.path.isdir(full) else "file"
        size = os.path.getsize(full) if os.path.isfile(full) else 0
        rows.append(f"  [{kind}] {name}  ({size} bytes)")
    if not rows:
        return f"(empty directory: {directory})"
    return f"{directory}/ contains {len(rows)} entries:\n" + "\n".join(rows)


if __name__ == "__main__":
    import sys

    print(list_files(sys.argv[1] if len(sys.argv) > 1 else "data"))
