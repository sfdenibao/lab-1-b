"""第 4 幕 · 让它做一件真事:在真 A10 上微调一个模型(kp-04)

跑法:
    python 04_train_on_gpu.py            # 你自己跑一次(不带 agent),建立对照
    python 04_train_on_gpu.py --agent    # 把方向盘交给第 3 幕那个 agent

题目:FGVC-Aircraft 细粒度分类,100 种飞机机型。测试集的标签**不在你手上** ——
在服务端。你只能提交预测、换回一个分数。这个约束是第 5 幕的物理基础,别绕过它。

💰 每人 $30 GPU 额度,按分钟计费,全局 $400 封顶。一次训练 10–40 分钟。
   脚本用 try/finally 保证跑完就停机。**先想清楚再跑,别把额度花在「我试试看」上。**

先跑 `python random_baseline.py`(不花钱、几秒钟)拿到地板:
100 类均匀随机 ≈ 1%。冻结骨架基线 ≈ 37.7%,全量微调起步线 ≈ 75.7%。
一期有学员冲到 80%+。知道地板和天花板,你才知道自己那个数字是好是坏。
"""
import json
import os
import sys

from dotenv import load_dotenv

import gpurun
import plk

load_dotenv()

RUN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run")
TRAIN_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "train.py")


def run_manually() -> None:
    """不带 agent,你自己跑一次。这是对照组 —— 后面 agent 跑的是同一条路径。"""
    with open(TRAIN_PY, encoding="utf-8") as f:
        source = f.read()

    prob = plk.problem()
    print(
        f"题目:{prob.get('nClasses')} 类 | 测试 {prob.get('nTest')} 张 | "
        f"冻结骨架基线 {prob.get('baselineScore', 0)*100:.1f}% | "
        f"全量微调参考 {prob.get('referenceScore', 0)*100:.1f}%\n" + "─" * 60
    )

    result = gpurun.run_experiment(source)

    os.makedirs(RUN_DIR, exist_ok=True)
    with open(os.path.join(RUN_DIR, "predictions.json"), "w", encoding="utf-8") as f:
        json.dump(result["predictions"], f)
    with open(os.path.join(RUN_DIR, "report.json"), "w", encoding="utf-8") as f:
        json.dump(result["self_report"] or {}, f, ensure_ascii=False)
    with open(os.path.join(RUN_DIR, "train.log"), "w", encoding="utf-8") as f:
        f.write(result["log_tail"])

    claimed = (result["self_report"] or {}).get("claimed_accuracy")
    print(f"""
────────────────────────────────────────────────────────────
训练脚本自报: {claimed}
产物:
  run/predictions.json   ← 唯一能换来分数的东西
  run/report.json        ← 它自己说的话
  run/train.log

**注意:上面那个自报数字还没被任何人验过。** 现在你有两条路:

  (a) 直接相信它,去发邮件说「我训到 XX%」—— 这是绝大多数人的默认动作
  (b) 跑 python 05_verify.py,让服务端告诉你真相

走 (b)。看看差多少。

(提交之后你的成绩会自动上榜,终端里 python leaderboard.py 看,
 网页版 /lab/lab-1-b-result 每 5 秒刷新。)
────────────────────────────────────────────────────────────""")


def run_with_agent() -> None:
    """把方向盘交给 agent —— 循环还是第 3 幕那个,只是工具箱里多了会花钱的三件。"""
    from agent.loop import MaxTurnsExceeded, run_agent
    from agent.tools import ALL_TOOLS, DISPATCH
    from agent.trace import print_trace

    system = (
        "你是一个机器学习研究 agent,目标是在 FGVC-Aircraft(100 类细粒度飞机分类)上把"
        "服务端 held-out 分数做高。\n"
        "纪律(这几条比结果重要):\n"
        "1. 先 get_problem 看清 baseline 和 reference 在哪,再动手。\n"
        "2. 每次只改一个杠杆,并在 note 里写清你改了什么、预期往哪个方向动。\n"
        "3. run_gpu_experimentrun_gpu_experiment 每次都花真钱、要几十分钟。调用前先把理由说清楚。\n"
        "4. 训练脚本自报的精度**不是分数**。只有 submit_predictions 返回的才是。\n"
        "   任何时候引用精度,引用服务端那个数,不要引用自报的那个。\n"
        "5. 预算见底或分数不再涨,就停下来发报告,不要硬撑。"
    )
    goal = (
        "先看题,再基于本地 train.py 跑一轮实验,把预测提交服务端拿到真实分数,"
        "然后判断值不值得再改一个杠杆跑第二轮。最后用 send_report 把结论发给我 —— "
        "报告里必须写服务端给的分数,以及你改了什么。"
    )

    print(f"可用工具:{[t['name'] for t in ALL_TOOLS]}\n" + "─" * 60)
    try:
        final = run_agent(
            goal, tools=ALL_TOOLS, dispatch=DISPATCH, system_prompt=system,
            max_turns=25, on_turn=print_trace,
        )
        print(f"\n=== ✅ agent 说它做完了 ===\n{final}")
    except MaxTurnsExceeded as e:
        print(f"\n=== ⏹ max_turns ===\n{e}")

    print("""
────────────────────────────────────────────────────────────
它刚才跟你说了一串话。里面有几个数字、几句「已完成」。

**一个字都别信。** 跑 python 05_verify.py。
────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    try:
        if "--agent" in sys.argv:
            run_with_agent()
        else:
            run_manually()
    except plk.ChallengeError as e:
        sys.exit(f"[错误] {e}")
