"""第 6 幕 · 把结果送到人手上,并留下回执(kp-06)

跑法:
    python 06_deliver.py          # 用 run/ 里已验证过的分数,发一封报告
    python 06_deliver.py --dry    # 只打印,不真发

投递本身很朴素:邮件 = SMTP 一封信;飞书 = 一个 POST 加一段 JSON。
真正要学的是它旁边那三件事。

## ① 渠道选择是部署决策,不是代码问题

    你在国外 / 沙箱在境外 → Gmail(GFW 挡的是从大陆访问 Google,不挡从境外发信)
    你在大陆读            → 飞书自定义机器人(app 里即时收到)

分叉点是「agent 在哪发」和「你在哪读」这两件事,和写什么代码无关。
改 config.yaml 的 delivery.channel 就行。

## ② 凭据即密码

应用专用密码、webhook URL —— 拿到就能用。它们进 .env(已被 .gitignore 挡),
**绝不进 git、不进日志、不进截图、不进你发给同学的报错信息**。
飞书 webhook URL 里那段 token 本身就是凭据,泄露 = 任何人都能往你群里发东西。

## ③ 发出去 ≠ 收得到

SMTP 回 250 只说明服务器**收下了**。进不进垃圾箱是 SPF/DKIM/发信信誉的事,
这一层看不见。所以 G2 闸只敢声称「服务器收下了」—— 闸绝不能声称它没证据的事。
你自己去邮箱里确认一眼,那才是端到端。
"""
import json
import os
import sys

import yaml
from dotenv import load_dotenv

import deliver
from verify import ledger

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.path.join(HERE, "run")


def build_body() -> tuple[str, str]:
    """报告里只放**过了闸的数字**。自报的那个不进正文。"""
    report_path = os.path.join(RUN_DIR, "report.json")
    report = {}
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)

    scored = ledger.latest(ledger.KIND_SCORE)
    if scored is None:
        sys.exit(
            "账本里没有服务端分数 —— 先跑 python 05_verify.py --only G1。\n"
            "这不是流程洁癖:没过 G1 就发报告,发出去的就是那个没人验过的数字。"
        )
    receipt = scored.get("receipt") or {}
    served = receipt.get("score", 0.0)

    import plk
    title = f"🛩 FGVC-Aircraft 实验报告 · 服务端 {served*100:.2f}%"
    body = (
        f"服务端 held-out 分数:{served*100:.2f}%\n"
        f"个人最佳:{(receipt.get('best') or 0)*100:.2f}%   当前名次:第 {receipt.get('rank', '?')} 名\n"
        f"榜单:{plk.BASE}/lab/lab-1-b-result\n"
        f"\n配置:backbone={report.get('backbone')} epochs={report.get('epochs')} "
        f"lr={report.get('lr')} freeze={report.get('freeze_backbone')}\n"
        f"备注:{report.get('note') or '(无)'}\n"
        f"\n(训练脚本自报 {report.get('claimed_accuracy')} —— 已由 G1 闸对账,以上以服务端为准。)\n"
    )
    return title, body


def main() -> None:
    with open(os.path.join(HERE, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    channel = (cfg.get("delivery") or {}).get("channel", "local")

    title, body = build_body()

    if "--dry" in sys.argv:
        print(f"[dry-run · channel={channel}]\n\n{title}\n\n{body}")
        return

    receipt = deliver.deliver(channel, title, body)
    ledger.record(ledger.KIND_DELIVERY, {"title": title, "channel": channel}, receipt)

    print(f"channel={channel}\n回执:{json.dumps(receipt, ensure_ascii=False, indent=2)}")
    if not receipt.get("ok"):
        sys.exit("\n投递失败。看上面的 reason —— 大多数时候是凭据没配,或者从这个网络连不上。")
    print("""
────────────────────────────────────────────────────────────
回执已进账本。跑 python 05_verify.py --only G2 看它变绿。

然后去你的邮箱/飞书**真的看一眼**。SMTP 250 只证明服务器收下了 ——
「发出去」和「你看到」之间还隔着一个垃圾箱。

下一幕:07_deploy.md —— 让它不用你手动跑。
────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    main()
