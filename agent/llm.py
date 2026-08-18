"""Parallight LLM 访问 —— Anthropic SDK 指向 Parallight 代理的薄封装。

没有魔法：代理就是一个 Anthropic Messages API 端点，我们只是设了 base_url + api_key。
P1 会先用裸 httpx POST 给你看「就是一个 HTTP 请求」，再用这里的 SDK 复现同一件事。
"""
from __future__ import annotations

import os
from typing import Any

from anthropic import Anthropic

DEFAULT_MODEL = "claude-haiku-4-5"  # 便宜够用（$1/$5）；重活用 SMART_MODEL
SMART_MODEL = "claude-sonnet-4-6"  # 写可跑代码 / 复杂循环（$3/$15）


def client() -> Anthropic:
    """构造一个指向 Parallight 代理的 Anthropic 客户端。"""
    key = os.environ.get("PARALLIGHT_API_KEY")
    base = os.environ.get("PARALLIGHT_BASE_URL")
    if not key or not base:
        raise RuntimeError(
            "PARALLIGHT_API_KEY / PARALLIGHT_BASE_URL 未设置 —— "
            "跑 /lab-start，或 `cp .env.example .env` 后填好。"
        )
    return Anthropic(api_key=key, base_url=base)


def complete(
    messages: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    system: str | None = None,
    tools: list[dict] | None = None,
):
    """发一次 Messages API 请求，返回完整 message（带 .usage / .stop_reason / .content）。"""
    kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools
    return client().messages.create(**kwargs)


def ask(prompt: str, *, model: str = DEFAULT_MODEL, max_tokens: int = 512, system: str | None = None) -> str:
    """最简单用法：进一段文字，出一段文字。"""
    msg = complete(
        [{"role": "user", "content": prompt}],
        model=model,
        max_tokens=max_tokens,
        system=system,
    )
    return "".join(b.text for b in msg.content if b.type == "text")
