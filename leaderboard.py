"""看成绩榜 —— 终端版。不花钱、不占提交额度。

    python leaderboard.py           # 看榜 + 你在第几
    python leaderboard.py --submit  # 先把 run/predictions.json 提交一次,再看榜

网页版:https://www.parallight.ai/lab/lab-1-b-result(每 5 秒自动刷新)

## 这张榜为什么算数

它上面那个数字**不是你算的**。测试集标签只在服务端 —— 你的训练脚本碰不到,
你的 agent 也碰不到。所以它是一个你造不出来、只能拿预测去换的东西。

这就是这条 lab 里「证据」的定义,第 5 幕 G1 闸认的也是它。
你本地那个 `report.json` 里的数字再好看,也只是自己说自己。
"""
import json
import os
import sys

import plk

RUN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run")
BOARD_URL = f"{plk.BASE}/lab/lab-1-b-result"


def submit_latest() -> None:
    path = os.path.join(RUN_DIR, "predictions.json")
    if not os.path.exists(path):
        sys.exit(f"没有 {path} —— 先跑 python 04_train_on_gpu.py 训一轮。")
    with open(path, encoding="utf-8") as f:
        preds = json.load(f)
    print(f"提交 {len(preds)} 条预测到服务端 held-out 打分器 ...")
    r = plk.submit(preds)
    mark = "  🎉 刷新个人最佳!" if r.get("improved") else ""
    print(
        f"  本次得分 {r.get('score', 0)*100:.2f}%{mark}\n"
        f"  个人最佳 {r.get('best', 0)*100:.2f}%  |  名次 第 {r.get('rank', '?')} 名  |  "
        f"今日提交 {r.get('attemptsToday', '?')}/{r.get('dailyCap', '?')}\n"
    )


def show_board() -> None:
    d = plk.leaderboard()
    board = d.get("board", [])
    you = d.get("you")
    ref = d.get("reference")
    budget = d.get("budget", 30)

    print(f"\n🛩  {d.get('name', 'FGVC-Aircraft')} 成绩榜   ({len(board)} 人上榜)")
    print(f"    参考线:冻结骨架 {(d.get('baseline') or 0)*100:.1f}%  |  "
          f"全量微调 {(ref or 0)*100:.1f}%  |  一期最好 >80%")
    print("─" * 72)
    print(f"{'名次':<6}{'学员':<34}{'accuracy':>10}{'提交':>6}{'GPU 花费':>14}")
    print("─" * 72)

    for r in board:
        me = r["email"] == d.get("youEmail")
        beat = ref is not None and r["score"] >= ref
        who = r["email"]
        if len(who) > 30:
            who = who[:29] + "…"
        tag = " (你)" if me else ""
        star = "✨" if beat else "  "
        print(
            f"{star}{r['rank']:<4}{who + tag:<34}"
            f"{r['score']*100:>9.2f}%{r['attempts']:>6}"
            f"{'$' + format(r['spentUsd'], '.2f') + '/' + str(budget):>14}"
        )

    print("─" * 72)
    if you:
        print(f"你:第 {you['rank']} 名 · {you['score']*100:.2f}% · "
              f"GPU 已花 ${you['spentUsd']:.2f}/{budget}(剩 ${you['remainingUsd']:.2f})")
    else:
        print("你还没上榜 —— python 04_train_on_gpu.py 训一轮,再 python leaderboard.py --submit")
    print("✨ = 超过全量微调参考线")
    print(f"\n网页版(每 5 秒自动刷新):{BOARD_URL}\n")


def main() -> None:
    try:
        if "--submit" in sys.argv:
            submit_latest()
        show_board()
    except plk.ChallengeError as e:
        sys.exit(f"[错误] {e}")


if __name__ == "__main__":
    main()
