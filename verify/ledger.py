"""证据账本 —— 这个 lab 的第五幕(kp-05)的地基。

## 为什么要有账本

agent 跑完一轮会跟你说三句话:

    「我训完了,精度 94%。」
    「报告已经发到你邮箱了。」
    「定时任务我部署好了,以后每天自己跑。」

这三句话都是 **token**。它生成「94%」和生成「今天天气不错」用的是同一套机制 ——
一个把下一个词接下去的函数。它没有能力区分「我真的做到了」和「这句话听起来很对」。

所以这一层的规矩只有一条:

    **每一句自述,必须配一条它自己造不出来的东西。**

那个东西叫**回执(receipt)**。回执的判据不是「看起来像真的」,而是「它得从外面拿」:

  · 分数    → 服务端 held-out 打分器返回的 score(测试标签不在这台机器上)
  · 投递    → SMTP 服务器返回的 message-id / 飞书返回的 code:0
  · 部署    → GitHub API 里那次 workflow run 的 run_id + conclusion

这三样 agent 都编不出来。编出来的立刻会在闸上对不上。

## 账本长什么样

一个 append-only 的 JSONL:`run/evidence.jsonl`。每行一条:

    {"ts": "...", "kind": "delivery", "claim": {...}, "receipt": {...}}

append-only 是故意的 —— 你要能回头看「它当时到底说了什么」,而不是只看最后一版。
出了事故,能改的日志等于没有日志。
"""
from __future__ import annotations

import datetime
import json
import os

LEDGER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run")
LEDGER_PATH = os.path.join(LEDGER_DIR, "evidence.jsonl")

# 账本认识的三类条目 —— 正好对应三道闸。
KIND_SCORE = "score"
KIND_DELIVERY = "delivery"
KIND_DEPLOY = "deploy"


def record(kind: str, claim: dict, receipt: dict | None) -> dict:
    """记一条。receipt=None 表示『它说了,但没拿出东西』—— 这条会让对应的闸变红。

    注意这个函数**不判断真假**,只如实记录。判断是闸的事。
    记录和裁决分开,是为了让你能翻到「它当时确实没给回执」这个事实本身。
    """
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "claim": claim,
        "receipt": receipt,
    }
    os.makedirs(LEDGER_DIR, exist_ok=True)
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load(kind: str | None = None) -> list[dict]:
    """读回账本。kind 给定就只要那一类。坏行跳过(账本坏了不该让闸崩掉)。"""
    if not os.path.exists(LEDGER_PATH):
        return []
    out = []
    with open(LEDGER_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind is None or e.get("kind") == kind:
                out.append(e)
    return out


def latest(kind: str) -> dict | None:
    """某一类最新的一条。闸看的是「最近这次跑」的证据,不是历史上曾经绿过。"""
    entries = load(kind)
    return entries[-1] if entries else None


def clear() -> None:
    """清空账本。第 5 幕开头故意用它 —— 让三道闸先红一次,你才知道闸是通电的。"""
    if os.path.exists(LEDGER_PATH):
        os.remove(LEDGER_PATH)
