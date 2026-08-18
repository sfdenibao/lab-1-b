"""第 5 幕 · Verify 是脊椎:自报的数字不是证据(kp-05)

跑法:
    python 05_verify.py --fresh    # 先清空账本,看三道闸**全红**
    python 05_verify.py            # 跑完实验/投递/部署之后,一道一道把它变绿
    python 05_verify.py --only G1  # 只跑一道

这一幕是整个 lab 的脊椎。前面四幕造出来的东西,到这里要接受一次不讲情面的验收。

## 为什么先要看它全红

一条从来没红过的闸,你分不清它是「真的过了」还是「压根没接线」。
**红 → 绿的那次跳变,才是信息。** 一上来就绿的闸,和一张写着「一切正常」的贴纸没区别。

这也是为什么 --fresh 是第一步而不是可选项。

## 三道闸各自在防什么

  G1 分数  防「量错了尺子」。它不是故意骗你 —— 手边最现成的精度是训练集上的,
           于是它报了那个。G1 拿它产出的 predictions 去服务端换真分,当面对账。

  G2 投递  防「函数 return True 就算发了」。认的是 SMTP 服务器的 250 回复 /
           飞书的 code:0 —— 外面给的东西。

  G3 部署  防「我部署好了」这四个没有信息量的字。不看仓库里有没有那个 yml,
           只看 GitHub Actions 里有没有一次真跑成功的 run。

三道闸的共同点:**都在问「拿出一个你自己造不出来的东西」。**
这句话可以搬到你以后做的任何一个 agent 上。
"""
import sys

from dotenv import load_dotenv

from verify import ledger
from verify.gates import gate_delivery, gate_deploy, gate_score

load_dotenv()

GATES = {"G1": gate_score, "G2": gate_delivery, "G3": gate_deploy}


def main() -> None:
    if "--fresh" in sys.argv:
        ledger.clear()
        print("已清空证据账本 —— 下面这三条**应该全红**。看清楚它们红的样子。\n")

    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].upper()

    verdicts = []
    for name, fn in GATES.items():
        if only and name != only:
            continue
        try:
            v = fn()
        except Exception as e:  # noqa: BLE001  闸自己崩了 = 红,绝不能算过
            from verify.gates import Verdict
            v = Verdict(name, False, f"闸自身异常({type(e).__name__}: {e})—— 记红,不记跳过。")
        verdicts.append(v)
        print(f"{v.mark}  {v.name}\n         {v.detail}\n")

    reds = [v for v in verdicts if not v.ok]
    print("─" * 60)
    if reds:
        print(f"{len(reds)}/{len(verdicts)} 道闸是红的。\n")
        print("不要改闸让它变绿 —— 那叫把温度计砸了退烧。去改被它挡住的那件事。")
        sys.exit(1)
    print(f"{len(verdicts)}/{len(verdicts)} 全绿。每一句自述都有一条外部证据顶着。")
    print("账本在 run/evidence.jsonl —— 那才是你交付的东西,不是那句「我做完了」。")
    print("成绩榜:python leaderboard.py(终端)/ /lab/lab-1-b-result(网页,5 秒自动刷新)")


if __name__ == "__main__":
    main()
