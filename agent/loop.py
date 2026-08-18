"""ReAct 控制循环 —— agent 的「会到底的循环」。

这就是第 3 幕的核心：think → 选工具 → 执行 → 喂回 → 重复，直到 stop。
三类 stop：① 模型自决 end_turn ② 工程兜底 max_turns ③ 异常（未知工具）。

整个文件不到 60 行。**agent 就这么点东西** —— 剩下的全是工具和 prompt。
第 4 幕之后你会给它接上真 GPU，它一行都不用改。
"""
from __future__ import annotations

from typing import Any, Callable

from agent.llm import SMART_MODEL, complete


class MaxTurnsExceeded(Exception):
    """stop ②：到了 max_turns 模型仍未 end_turn。"""


class UnknownToolError(Exception):
    """stop ③：模型请求了 dispatch 里没有的工具。"""


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text")


def run_agent(
    goal: str,
    *,
    tools: list[dict],
    dispatch: dict[str, Callable[..., str]],
    system_prompt: str = "",
    model: str = SMART_MODEL,
    max_turns: int = 12,
    max_tokens: int = 2048,
    on_turn: Callable[[Any, int], None] = lambda resp, turn: None,
) -> str:
    """跑 ReAct 循环，返回模型最终文本。"""
    messages: list[dict[str, Any]] = [{"role": "user", "content": goal}]

    for turn in range(1, max_turns + 1):
        resp = complete(messages, model=model, max_tokens=max_tokens, system=system_prompt or None, tools=tools)
        on_turn(resp, turn)
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            return _text(resp)
        if resp.stop_reason != "tool_use":
            return _text(resp)  # 非预期 stop：拿到啥文本就返回，别崩

        results: list[dict[str, Any]] = []
        for tu in (b for b in resp.content if b.type == "tool_use"):
            if tu.name not in dispatch:
                raise UnknownToolError(
                    f"模型请求了未知工具 {tu.name!r}。可用：{list(dispatch.keys())}"
                )
            try:
                output = dispatch[tu.name](**tu.input)
            except Exception as e:  # noqa: BLE001  把异常吞成 agent 能看见的字符串
                output = f"Error: {type(e).__name__}: {e}"
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": str(output)})
        messages.append({"role": "user", "content": results})

    raise MaxTurnsExceeded(f"ReAct 循环跑满 {max_turns} 轮仍未 end_turn")
