"""无人值守入口 —— GitHub Actions 每天叫醒的就是这个文件(kp-07)。

    python autopilot.py            # 默认:只播报,不碰 GPU,不花钱  ← 定时器跑的是这个
    python autopilot.py --train    # 完整一轮:训练 → 验证 → 播报   ← 只能手动触发

## 为什么默认模式不训练:别让定时器有权花钱

一个每天 09:17 自动触发、能启动 A10 的 workflow,是一台每天自动扣你几美元的机器。
你睡着的时候它也在跑;cron 写错成每小时一次,你第二天醒来额度就没了;
仓库被 fork、secret 被误配到 public,别人也能替你烧。

所以这里做了一道**结构性**的闸,不是提醒:

    schedule 触发   → 没有 --train → 物理上走不到 run_experiment
    手动 dispatch   → 你在页面上勾 train=true 才带 --train

注意这道闸的形状:不是「在 prompt 里叮嘱它别乱花钱」,也不是「加个 if 判断预算」,
而是**让定时那条路径根本没有那个能力**。和第 2 幕的结论是同一条:
限制 agent 能做什么,靠的是不给它那个函数,不是靠求它。

## 默认模式在干嘴:轻量播报

  · 查一眼榜单站位(免费)
  · 把上一次跑的证据(服务端分数、投递回执)整理成一条日报
  · 发出去、记账

它每天证明的是「这套东西还活着、证据链还连着」。这本身就有价值 ——
一个悄悄挂掉三周没人发现的定时任务,比没有定时任务更糟。
"""
from __future__ import annotations

import json
import os
import sys

import yaml
from dotenv import load_dotenv

import deliver
import plk
from verify import ledger

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.path.join(HERE, "run")


def _channel() -> str:
    try:
        with open(os.path.join(HERE, "config.yaml"), encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return (cfg.get("delivery") or {}).get("channel", "local")
    except Exception:  # noqa: BLE001
        return "local"


# ── 默认模式:只播报 ──────────────────────────────────────────────────────────

def report_only() -> str:
    """零 GPU 成本。把「上次跑到哪、证据还在不在」讲一遍。"""
    lines = ["📡 Auto-ML 日报", ""]

    try:
        prob = plk.problem()
        lines.append(
            f"题目参考线:冻结骨架 {prob.get('baselineScore', 0)*100:.1f}% / "
            f"全量微调 {prob.get('referenceScore', 0)*100:.1f}%"
        )
    except plk.ChallengeError as e:
        lines.append(f"⚠️ 拉不到题目信息:{e}")

    scored = ledger.latest(ledger.KIND_SCORE)
    if scored:
        r = scored.get("receipt") or {}
        lines += [
            "",
            f"最近一次服务端分数:{(r.get('score') or 0)*100:.2f}%",
            f"个人最佳:{(r.get('best') or 0)*100:.2f}%   名次:第 {r.get('rank', '?')} 名",
            f"记录时间:{scored.get('ts')}",
        ]
    else:
        lines += ["", "⚠️ 账本里还没有任何服务端分数 —— 这条链是断的,去跑一轮实验。"]

    delivered = ledger.latest(ledger.KIND_DELIVERY)
    if delivered:
        lines.append(f"上次投递:{delivered.get('ts')}(回执 ok={(delivered.get('receipt') or {}).get('ok')})")

    return "\n".join(lines)


# ── --train 模式:完整一轮 ────────────────────────────────────────────────────

def full_round() -> str:
    """训练 → 服务端验证 → 汇报。**只应该被手动触发。**"""
    import gpurun
    from verify.gates import gate_score

    with open(os.path.join(HERE, "train.py"), encoding="utf-8") as f:
        source = f.read()

    result = gpurun.run_experiment(source)

    os.makedirs(RUN_DIR, exist_ok=True)
    with open(os.path.join(RUN_DIR, "predictions.json"), "w", encoding="utf-8") as f:
        json.dump(result["predictions"], f)
    with open(os.path.join(RUN_DIR, "report.json"), "w", encoding="utf-8") as f:
        json.dump(result["self_report"] or {}, f, ensure_ascii=False)

    verdict = gate_score(
        os.path.join(RUN_DIR, "predictions.json"),
        os.path.join(RUN_DIR, "report.json"),
    )
    ev = verdict.evidence
    return "\n".join([
        "🛩 Auto-ML 完整一轮",
        "",
        f"G1 分数闸:{verdict.mark.strip()}",
        f"  {verdict.detail}",
        "",
        f"服务端分数(唯一算数的那个):{(ev.get('served') or 0)*100:.2f}%",
        f"训练脚本自报:{(ev.get('claimed') or 0)*100:.2f}%",
        f"GPU 剩余额度:${result['remainingUsd']:.4f}",
    ])


def main() -> None:
    train = "--train" in sys.argv
    if train and os.environ.get("AUTOPILOT_ALLOW_GPU") != "1":
        # 双保险:除了命令行要显式带 --train,环境里还得开 AUTOPILOT_ALLOW_GPU。
        # 一道闸会被误触,两道不同来源的闸不容易同时误触。
        sys.exit(
            "拒绝执行 --train:环境变量 AUTOPILOT_ALLOW_GPU 不等于 1。\n"
            "这是防止定时任务误烧 GPU 额度的第二道闸 —— 手动跑请显式 "
            "AUTOPILOT_ALLOW_GPU=1 python autopilot.py --train"
        )

    body = full_round() if train else report_only()
    title = "🛩 Auto-ML 完整一轮" if train else "📡 Auto-ML 日报"

    channel = _channel()
    receipt = deliver.deliver(channel, title, body)
    ledger.record(ledger.KIND_DELIVERY, {"title": title, "channel": channel, "mode":
                                         "train" if train else "report"}, receipt)

    print(body)
    print(f"\n[deliver] channel={channel} ok={receipt.get('ok')} {receipt.get('reason') or ''}")
    if not receipt.get("ok"):
        # 投递失败要让 Actions 变红。静默成功的定时任务 = 你以为它在跑。
        sys.exit(1)


if __name__ == "__main__":
    main()
