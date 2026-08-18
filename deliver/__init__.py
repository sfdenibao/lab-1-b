"""投递渠道分发 —— 同一份报告,发到哪取决于「你在哪发、你在哪读」。

这是一个**部署决策**,不是代码问题:
  · 在国外 / 沙箱在境外 → Gmail SMTP 最顺(GFW 挡的是从大陆访问 Google,不挡从境外发信)
  · 在大陆读            → 飞书自定义机器人,app 里即时收到
  · 没配任何凭据        → local 兜底,只写本地文件

⚠️ 每个 push() 都必须返回**回执**,不是 True/False。
   第 5 幕的 G2 闸认的是 message-id / code:0 这种外部给的东西 ——
   「我返回了 True」不是证据,那还是自己说自己。
"""
from __future__ import annotations

from . import feishu, mailer


def deliver(channel: str, title: str, body: str) -> dict:
    """返回统一形状的回执:{ok, channel, ...渠道特有字段}。"""
    if channel in ("gmail", "email", "smtp"):
        return {**mailer.push(title, body), "channel": "gmail"}
    if channel == "feishu":
        return {**feishu.push(title, body), "channel": "feishu"}
    if channel == "local":
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run", "report.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {title}\n\n{body}\n")
        # ok=True 但**没有外部回执** —— G2 会因此判红,这是故意的:
        # 写本地文件不叫「送到人手上」。
        return {"ok": True, "channel": "local", "path": path}
    return {"ok": False, "channel": channel, "reason": f"未知 channel: {channel}(用 gmail / feishu / local)"}
