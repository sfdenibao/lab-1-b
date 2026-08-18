"""Parallight 挑战服务的薄客户端 —— 全 lab 唯一的一份。

这一层为什么值得单独抽出来:后面**三个不同的地方**要调它,而且必须是同一份:

  ① agent 的工具(agent/tools/gpu.py)     —— agent 自己去开 GPU、跑训练、提交分数
  ② 你手动跑的编排器(04_train_on_gpu.py) —— 你自己不带 agent 跑一遍,建立对照
  ③ Verify 闸(verify/gate_score.py)      —— 独立复算 agent 报的那个分

③ 尤其关键:闸必须能**绕开 agent** 自己去问服务端要分。如果闸读的是 agent 写的文件,
那它就不是闸,是复读机。

服务端有你**拿不到**的测试集标签(held-out)。你只能提交预测、拿回一个分数。
这就是「证据」的物理基础 —— 一个你造不出来、只能去换的数字。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("PARALLIGHT_LAB_BASE", "https://www.parallight.ai").rstrip("/")
CHALLENGE_PREFIX = f"{BASE}/lab/api/lab/challenge"


class ChallengeError(RuntimeError):
    """服务端拒绝了这次请求(HTTP 非 2xx)。带上服务端说的人话原因。"""


# ── 身份 ─────────────────────────────────────────────────────────────────────

def find_token() -> str | None:
    """依次找 env → ~/.parallight/auth.json → ~/.claude/settings.json 里的 plk_ token。

    在线 lab 里 /lab-start 会自动注入,通常你什么都不用做。
    """
    t = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("PARALLIGHT_API_KEY")
    if t and t.startswith("plk_"):
        return t
    for path in (
        os.path.expanduser("~/.parallight/auth.json"),
        os.path.expanduser("~/.claude/settings.json"),
    ):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        for key in ("proxy_token", "lab_gateway_token", "ANTHROPIC_AUTH_TOKEN"):
            v = d.get(key) or (d.get("env", {}) or {}).get(key)
            if isinstance(v, str) and v.startswith("plk_"):
                return v
    return None


def require_token() -> str:
    tok = find_token()
    if not tok:
        raise ChallengeError(
            "没找到身份 token(plk_)。在线 lab 里应自动有;"
            "本地 dogfood 请设 ANTHROPIC_AUTH_TOKEN=plk_xxx"
        )
    return tok


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _request(method: str, path: str, token: str, body: dict | None = None, timeout: int = 60) -> dict:
    url = f"{CHALLENGE_PREFIX}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", str(e.code))
        except Exception:
            msg = str(e.code)
        raise ChallengeError(f"HTTP {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise ChallengeError(f"连不上 {BASE}: {e.reason}") from None


def get(path: str, token: str | None = None, **kw) -> dict:
    return _request("GET", path, token or require_token(), **kw)


def post(path: str, token: str | None = None, body: dict | None = None, **kw) -> dict:
    return _request("POST", path, token or require_token(), body=body or {}, **kw)


# ── 题目 / 打分 ───────────────────────────────────────────────────────────────

def problem(token: str | None = None) -> dict:
    """题目元信息。字段是 camelCase:nClasses / nTest / baselineScore / referenceScore。"""
    return get("problem", token)


def leaderboard(token: str | None = None) -> dict:
    """读成绩榜。返回 {board:[{rank,email,score,attempts,spentUsd,remainingUsd}], you, ...}。

    注意这个接口的路径和上面几个不一样(不在 /challenge/ 下面而是同级),
    所以它自己组装 URL 而不是走 get()。
    """
    tok = token or require_token()
    url = f"{BASE}/lab/api/lab/challenge/leaderboard"
    req = urllib.request.Request(
        url, headers={"authorization": f"Bearer {tok}", "content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise ChallengeError("成绩榜仅向报名学员开放(你的账号是 visitor)") from None
        raise ChallengeError(f"HTTP {e.code} 读榜失败") from None
    except urllib.error.URLError as e:
        raise ChallengeError(f"连不上 {BASE}: {e.reason}") from None


def submit(predictions: list[int], token: str | None = None) -> dict:
    """把预测提交给服务端 held-out 打分器。

    返回 {score, best, rank, improved, attemptsToday, dailyCap}。
    **这是本 lab 唯一算数的分数来源。** 任何别的数字(包括训练脚本自己打印的
    top1、agent 在报告里写的 accuracy)都只是一段文本,不是证据。
    """
    return post("submit", token, body={"predictions": [int(p) for p in predictions]})


# ── GPU 沙箱 ─────────────────────────────────────────────────────────────────

def gpu_start(token: str | None = None) -> dict:
    return post("gpu/start", token, body={})


def gpu_status(token: str | None = None) -> dict:
    """注意 live ≠ ready。live 只代表『沙箱已建、开始计费』;
    ready 才代表『真能 SSH 进去跑命令』。等的是 ready。"""
    return get("gpu/status", token)


def gpu_upload(path: str, content: str, token: str | None = None) -> dict:
    return post("gpu/upload", token, body={"path": path, "content": content})


def gpu_run(command: str, background: bool = True, token: str | None = None) -> dict:
    return post("gpu/run", token, body={"command": command, "background": background})


def gpu_logs(token: str | None = None) -> str:
    return gpu_logs_raw(token).get("log", "")


def gpu_logs_raw(token: str | None = None) -> dict:
    return get("gpu/logs", token)


def gpu_fetch(path: str, token: str | None = None) -> dict:
    return post("gpu/fetch", token, body={"path": path})


def gpu_stop(token: str | None = None) -> dict:
    return post("gpu/stop", token)
