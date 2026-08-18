"""接线自检 —— 不联网、不花钱、不调模型,几秒钟跑完。

    python smoke_test.py

它验的不是「你学会了」,而是「这套代码本身没散架」:
工具注册表对得上、账本能读写、三道闸在**没有证据时确实是红的**。

最后那一条是关键。一个「缺证据就跳过」的闸,会在你什么都没做的时候给你绿灯 ——
那是所有验收系统里最贵的一个 bug。所以它在这里被当成一条硬断言测。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main() -> None:
    print("[1] 工具注册表")
    from agent.tools import ALL_TOOLS, COSTLY_TOOLS, DISPATCH, SAFE_TOOLS

    names = [t["name"] for t in ALL_TOOLS]
    check("每个 schema 都有对应的 dispatch 函数",
          all(n in DISPATCH for n in names),
          f"缺:{[n for n in names if n not in DISPATCH]}")
    check("每个 dispatch 函数都有对应的 schema",
          all(n in names for n in DISPATCH),
          f"多:{[n for n in DISPATCH if n not in names]}")
    check("工具名无重复", len(names) == len(set(names)))
    check("SAFE + COSTLY == ALL", len(SAFE_TOOLS) + len(COSTLY_TOOLS) == len(ALL_TOOLS))
    check("send_report 的 schema 里没有收件人字段(第 6 幕的执行层防线)",
          "to" not in (
              next(t for t in ALL_TOOLS if t["name"] == "send_report")["input_schema"]
              .get("properties", {})
          ))
    check("会花钱的工具在 description 里明说了成本",
          all("COST" in t["description"].upper() or "money" in t["description"].lower()
              for t in COSTLY_TOOLS if t["name"] == "run_gpu_experiment"))
    check("看榜工具归在 SAFE(免费,不该和花钱的混在一起)",
          "view_leaderboard" in [t["name"] for t in SAFE_TOOLS]
          and "view_leaderboard" not in [t["name"] for t in COSTLY_TOOLS])

    print("\n[2] 证据账本")
    from verify import ledger

    backup = None
    if os.path.exists(ledger.LEDGER_PATH):
        with open(ledger.LEDGER_PATH, encoding="utf-8") as f:
            backup = f.read()
    try:
        ledger.clear()
        check("空账本 latest() 返回 None", ledger.latest(ledger.KIND_SCORE) is None)
        ledger.record(ledger.KIND_DELIVERY, {"title": "t"}, {"ok": True, "channel": "local"})
        e = ledger.latest(ledger.KIND_DELIVERY)
        check("写进去读得回来", e is not None and e["claim"]["title"] == "t")
        check("按 kind 隔离", ledger.latest(ledger.KIND_SCORE) is None)
        check("append-only(两条不覆盖)",
              (ledger.record(ledger.KIND_DELIVERY, {"title": "u"}, None),
               len(ledger.load(ledger.KIND_DELIVERY)) == 2)[1])

        print("\n[3] 三道闸在没有证据时必须是红的")
        from verify.gates import gate_delivery, gate_deploy, gate_score

        ledger.clear()
        v1 = gate_score("run/__nonexistent__.json", "run/__nonexistent__.json")
        check("G1 缺产物 → 红(不是跳过)", not v1.ok, v1.detail)
        v2 = gate_delivery()
        check("G2 空账本 → 红", not v2.ok, v2.detail)

        # G3:临时清掉环境变量,确认它红而不是崩
        saved = {k: os.environ.pop(k, None) for k in ("BROADCAST_REPO", "GITHUB_PERSONAL_ACCESS_TOKEN")}
        try:
            v3 = gate_deploy()
            check("G3 缺配置 → 红", not v3.ok, v3.detail)
        finally:
            for k, val in saved.items():
                if val is not None:
                    os.environ[k] = val

        # local 渠道写了文件,但 G2 仍应判红 —— 写本地文件不叫「送到人手上」
        ledger.clear()
        ledger.record(ledger.KIND_DELIVERY, {"title": "t"}, {"ok": True, "channel": "local"})
        check("G2 对 channel=local 判红(有 ok 但无外部回执)", not gate_delivery().ok)

        # 邮件渠道:自己写的 message_id 不算回执,必须要服务器的 250
        ledger.clear()
        ledger.record(ledger.KIND_DELIVERY, {"title": "t"},
                      {"ok": True, "channel": "gmail", "message_id": "<self-made@x>"})
        check("G2 只有自造 message_id → 红", not gate_delivery().ok)
        ledger.clear()
        ledger.record(ledger.KIND_DELIVERY, {"title": "t"},
                      {"ok": True, "channel": "gmail", "to": "a@b.c",
                       "smtp_code": 250, "smtp_response": "2.0.0 OK 173... - gsmtp"})
        check("G2 有服务器 250 回执 → 绿", gate_delivery().ok)
    finally:
        ledger.clear()
        if backup is not None:
            os.makedirs(ledger.LEDGER_DIR, exist_ok=True)
            with open(ledger.LEDGER_PATH, "w", encoding="utf-8") as f:
                f.write(backup)

    print("\n[4] G1 对账逻辑(把服务端换成假的,不联网、不占提交额度)")
    import json
    import tempfile

    import plk
    from verify.gates import gate_score

    real_submit = plk.submit
    tmp = tempfile.mkdtemp()
    pred_p = os.path.join(tmp, "predictions.json")
    rep_p = os.path.join(tmp, "report.json")
    with open(pred_p, "w") as f:
        json.dump([1, 2, 3], f)

    def fake(score):
        return lambda preds, token=None: {"score": score, "best": score, "rank": 7}

    try:
        # ① 自报训练集精度 → 和服务端差 34 个点 → 必须红
        with open(rep_p, "w") as f:
            json.dump({"claimed_accuracy": 0.94}, f)
        plk.submit = fake(0.60)
        v = gate_score(pred_p, rep_p)
        check("自报 0.94 / 服务端 0.60 → 红", not v.ok, v.detail)
        check("红的时候把落差摆出来", "0.34" in v.detail or "34" in v.detail, v.detail)

        # ② 自报自切 val 精度 → 差 1 个点 → 绿
        with open(rep_p, "w") as f:
            json.dump({"claimed_accuracy": 0.61}, f)
        plk.submit = fake(0.60)
        check("自报 0.61 / 服务端 0.60 → 绿", gate_score(pred_p, rep_p).ok)

        # ③ 服务端拿不到分 → 红,绝不能当成「验过了」
        def boom(preds, token=None):
            raise plk.ChallengeError("daily cap reached")
        plk.submit = boom
        v = gate_score(pred_p, rep_p)
        check("服务端打分失败 → 红(不是跳过)", not v.ok, v.detail)

        # ④ report 里没有可比数字 → 红
        with open(rep_p, "w") as f:
            json.dump({"note": "跑完了"}, f)
        plk.submit = fake(0.60)
        check("report 无 claimed_accuracy → 红", not gate_score(pred_p, rep_p).ok)
    finally:
        plk.submit = real_submit
        ledger.clear()
        if backup is not None:
            os.makedirs(ledger.LEDGER_DIR, exist_ok=True)
            with open(ledger.LEDGER_PATH, "w", encoding="utf-8") as f:
                f.write(backup)

    print("\n[5] 投递渠道分发")
    import deliver
    r = deliver.deliver("nope", "t", "b")
    check("未知渠道返回 ok=False 且说人话", r["ok"] is False and "未知" in r["reason"])

    print("\n" + "─" * 60)
    if FAILS:
        print(f"✗ {len(FAILS)} 项没过:{FAILS}")
        sys.exit(1)
    print("✓ 接线全通。可以开始第 1 幕了:python 01_llm.py")


if __name__ == "__main__":
    main()
