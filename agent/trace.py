"""print_trace —— 把一轮 agent 响应透明化打印（💭 想法 / 🔧 工具调用 / stop_reason+token）。"""
from __future__ import annotations


def _short(obj, n: int = 160) -> str:
    s = str(obj)
    return s if len(s) <= n else s[:n] + "…"


def print_trace(resp, turn: int) -> None:
    for b in resp.content:
        if b.type == "text" and b.text.strip():
            print(f"[turn {turn}] 💭 {_short(b.text.strip(), 300)}")
        elif b.type == "tool_use":
            print(f"[turn {turn}] 🔧 {b.name}({_short(b.input)})")
    usage = getattr(resp, "usage", None)
    itok = getattr(usage, "input_tokens", 0)
    otok = getattr(usage, "output_tokens", 0)
    print(f"[turn {turn}] stop_reason={resp.stop_reason}  tokens in/out={itok}/{otok}")
