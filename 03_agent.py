"""第 3 幕 · agent = LLM + 工具 + 循环 + 停止条件(kp-03)

跑法:
    python 03_agent.py
    python 03_agent.py "看一眼 train.py,告诉我哪几个超参可调、各自大概往哪个方向影响精度"

第 2 幕那个手工循环,套一个 while,就是 agent。全部代码在 agent/loop.py,不到 60 行。
打开它看一眼 —— 你会发现里面没有任何你没见过的东西。

**这一幕只给安全工具**(读目录/写文件/跑 python/受限 shell),不给 GPU、不给发信。
理由:先在便宜的地方把这个循环看透。第 4 幕再把贵的工具接上去,循环一行都不用改。

三类停止,跑的时候留意 stop_reason:
    ① end_turn    模型自己认为做完了     —— 它说了算
    ② max_turns   跑满轮数,工程兜底     —— 你说了算(没有这条它可能无限烧钱)
    ③ 异常        请求了 DISPATCH 里没有的工具
"""
import sys

from dotenv import load_dotenv

from agent.loop import MaxTurnsExceeded, run_agent
from agent.tools import DISPATCH, SAFE_TOOLS
from agent.trace import print_trace

load_dotenv()

SYSTEM = (
    "你是一个动手型的机器学习工程 agent。你可以列目录、读写文件、跑 Python、"
    "跑受限 shell。一步只做一个动作,看到工具结果再决定下一步;"
    "遇到以 'Error:' 开头的结果就读懂它、调整后重试,不要重复同一个失败动作。"
    "做完用一段话说清你做了什么、结论是什么、证据在哪个文件里。"
)

DEFAULT_GOAL = (
    "读一下当前目录的 train.py,找出所有标了 # TUNE 的可调超参。"
    "对每一个,用一句话说明它往哪个方向调会提高精度、代价是什么。"
    "把结论写成一个表格,存到 run/tuning-notes.md。"
)


def main() -> None:
    goal = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GOAL
    print(f"目标:{goal}\n可用工具:{[t['name'] for t in SAFE_TOOLS]}\n" + "─" * 60)
    try:
        final = run_agent(
            goal,
            tools=SAFE_TOOLS,
            dispatch=DISPATCH,
            system_prompt=SYSTEM,
            max_turns=15,
            on_turn=print_trace,
        )
        print("\n=== ✅ end_turn(模型自己认为做完了)===")
        print(final)
    except MaxTurnsExceeded as e:
        print(f"\n=== ⏹ max_turns(工程兜底刹车)===\n{e}")

    print("""
────────────────────────────────────────────────────────────
往上翻,把每一轮的 🔧 连起来看 —— 那就是它的「思路」。没有别的东西了。

现在你已经有一个完整的 agent 了。它唯一的问题是:**它还没做过任何一件真事。**
下一幕给它一台真 GPU:python 04_train_on_gpu.py
────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    main()
