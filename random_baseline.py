"""随机 baseline —— 先摸清地板。不碰 GPU、不花一分钱、几秒钟出结果。

    python random_baseline.py

**先跑这个再动 train.py。** 理由不是仪式感:
后面你会拿到一个数字(比如 61%),这个数字是好是坏,取决于地板和天花板在哪。
不知道地板,任何分数都只是一个数字。

顺带这也是你第一次亲手用服务端打分器 —— 注意你提交的是**随机猜的预测**,
服务端照样给分。它不关心你怎么来的,只关心预测本身。这就是 held-out 打分的性质:
它验的是结果,不是你的说法。
"""
import random
import sys

import plk


def main() -> None:
    try:
        prob = plk.problem()
        n_classes, n_test = prob["nClasses"], prob["nTest"]
        preds = [random.randrange(n_classes) for _ in range(n_test)]
        res = plk.submit(preds)
    except plk.ChallengeError as e:
        sys.exit(f"[错误] {e}")

    score = res.get("score", 0)
    print(f"随机 baseline:{score * 100:.2f}%   (100 类均匀随机的理论期望 ≈ {100 / n_classes:.2f}%)")
    print(
        "\n地板和参考线:\n"
        f"  随机          ≈ {100 / n_classes:.1f}%   ← 你刚拿到的\n"
        f"  冻结骨架       ≈ {prob.get('baselineScore', 0) * 100:.1f}%   ← 只训分类头(便宜)\n"
        f"  全量微调起步线 ≈ {prob.get('referenceScore', 0) * 100:.1f}%   ← 让梯度流过预训练层\n"
        "  一期最好成绩    > 80%\n"
        "\n中间那两个数的差,就是「让梯度流过预训练层」这一个决定值多少钱。"
    )


if __name__ == "__main__":
    main()
