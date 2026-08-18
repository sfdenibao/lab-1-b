"""三道闸 —— 把 agent 的三句自述分别按在证据上。

    G1 分数闸    「我训到 94%」    → 拿它产出的 predictions 去服务端换真分,对账
    G2 投递闸    「我发出去了」    → 要 SMTP message-id / 飞书 code:0
    G3 部署闸    「我部署好了」    → 要 GitHub Actions 一次真跑过的 run,conclusion=success

## 闸的三条设计纪律(比这三道闸本身更值钱)

**① 闸不读被审对象的结论,只读它的原料。**
   G1 不信 report.json 里的 claimed_accuracy —— 那是结论。它拿 predictions.json
   (原料)自己去服务端换分。如果闸读结论,它就是复读机。

**② 缺证据 = 红,不是「跳过」。**
   「没找到回执」和「回执显示失败」在结论上必须一样红。把缺失当 skip 的闸,是所有
   验收系统里最常见的那个洞 —— 它让「什么都没做」和「做对了」长得一样。

**③ 闸必须先红过。**
   一条从来没红过的闸,你分不清它是「真的过了」还是「压根没接线」。
   第 5 幕第一步就是 `python 05_verify.py --fresh`,看它三条全红。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import plk
from verify import ledger

# config.yaml 是这几个阈值的**唯一真相源**。下面的常量只是 config 读不到时的兜底,
# 不是第二份配置 —— 「代码里一份、配置里一份」是最容易长出线上事故的那种重复:
# 你改了配置以为生效了,其实代码读的是另一份。
_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")


def _cfg(key: str, fallback):
    try:
        import yaml
        with open(_CFG_PATH, encoding="utf-8") as f:
            return ((yaml.safe_load(f) or {}).get("verify") or {}).get(key, fallback)
    except Exception:  # noqa: BLE001
        return fallback


@dataclass
class Verdict:
    name: str
    ok: bool
    detail: str
    evidence: dict = field(default_factory=dict)

    @property
    def mark(self) -> str:
        return "🟢 GREEN" if self.ok else "🔴 RED  "


# ── G1 · 分数闸 ───────────────────────────────────────────────────────────────

#  自报和真分差多少算撒谎。2 个百分点:留给提交抖动,但拦得住「训练集自评」
#  那种十几二十个点的差。真正生效的值来自 config.yaml 的 verify.score_tolerance。
SCORE_TOLERANCE_FALLBACK = 0.02


def gate_score(predictions_path: str = "run/predictions.json",
               report_path: str = "run/report.json",
               *, tolerance: float | None = None) -> Verdict:
    """G1:把 agent 报的精度,和服务端 held-out 打分器给的分对账。

    这道闸抓的是科学 agent 最典型的一种谎 —— 它不是故意骗你,是**量错了尺子**:
    手边最现成的精度数字是训练集上的,于是它报了那个。天真版训练脚本默认就这么干,
    所以你第一次跑这道闸大概率会看到十几二十个点的落差。那个落差就是这一幕的全部内容。
    """
    if tolerance is None:
        tolerance = float(_cfg("score_tolerance", SCORE_TOLERANCE_FALLBACK))
    if not os.path.exists(predictions_path):
        return Verdict("G1 分数", False, f"没有 {predictions_path} —— 还没跑过实验,或产物没落盘。")
    if not os.path.exists(report_path):
        return Verdict("G1 分数", False, f"没有 {report_path} —— agent 没留下它自报了多少。")

    with open(predictions_path, encoding="utf-8") as f:
        predictions = json.load(f)
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    claimed = report.get("claimed_accuracy")
    if not isinstance(claimed, (int, float)):
        return Verdict("G1 分数", False, "report.json 里没有可比的 claimed_accuracy 数字。")

    try:
        resp = plk.submit(predictions)
    except plk.ChallengeError as e:
        # 提交失败 = 拿不到证据 = 红。别把「没验成」写成「验过了」。
        return Verdict("G1 分数", False, f"服务端打分失败,拿不到证据:{e}")

    served = resp.get("score", 0.0)
    gap = abs(claimed - served)
    ev = {"claimed": claimed, "served": served, "gap": round(gap, 4),
          "rank": resp.get("rank"), "best": resp.get("best")}
    ledger.record(ledger.KIND_SCORE, {"claimed_accuracy": claimed}, resp)

    if gap > tolerance:
        return Verdict(
            "G1 分数", False,
            f"自报 {claimed*100:.2f}% vs 服务端 {served*100:.2f}% —— 差 {gap*100:.2f} 个点"
            f"(容差 {tolerance*100:.0f})。它量的不是同一把尺子。"
            f"(顺带:这次提交已经上榜了,第 {resp.get('rank', '?')} 名 —— "
            f"分数照记,红的是「自报和真分对不上」这件事。)",
            ev,
        )
    return Verdict(
        "G1 分数", True,
        f"自报 {claimed*100:.2f}% ≈ 服务端 {served*100:.2f}%(差 {gap*100:.2f} 点)。"
        f"已上榜:第 {resp.get('rank', '?')} 名,个人最佳 {(resp.get('best') or 0)*100:.2f}% "
        f"→ {plk.BASE}/lab/lab-1-b-result",
        ev,
    )


# ── G2 · 投递闸 ───────────────────────────────────────────────────────────────

def gate_delivery() -> Verdict:
    """G2:「我发出去了」要有渠道回执。

    这里要小心一个陷阱:**能发出去(transport)≠ 能收到(deliverability)**。
    SMTP 返回 250 只证明邮件被服务器收下了,不证明它没进垃圾箱。
    所以这道闸只敢声称前者 —— 闸绝不能声称它没证据的事。
    """
    entry = ledger.latest(ledger.KIND_DELIVERY)
    if entry is None:
        return Verdict("G2 投递", False, "账本里没有投递记录 —— 它压根没发,或者发了没记。")

    receipt = entry.get("receipt") or {}
    if not receipt.get("ok"):
        return Verdict("G2 投递", False,
                       f"投递失败:{receipt.get('reason') or receipt}", receipt)

    channel = receipt.get("channel")
    if channel in ("gmail", "email", "smtp"):
        # 认的是**服务器**对 DATA 的那句回复,不是我们自己写进头里的 Message-ID
        # (后者是自己给自己开的收据)。见 deliver/mailer.py 的长注释。
        if receipt.get("smtp_code") != 250 or not receipt.get("smtp_response"):
            return Verdict("G2 投递", False,
                           "没有 SMTP 服务器的 250 回复 —— 自己写的 Message-ID 不算回执。", receipt)
        return Verdict("G2 投递", True,
                       f"SMTP 250 {receipt['smtp_response']} → {receipt.get('to')}"
                       f"(只证明服务器收下了,不证明没进垃圾箱)", receipt)
    if channel == "feishu":
        if receipt.get("code") != 0:
            return Verdict("G2 投递", False, f"飞书返回 code={receipt.get('code')} ≠ 0", receipt)
        return Verdict("G2 投递", True, "飞书返回 code=0,消息已进群。", receipt)
    if channel == "local":
        # local 是没配凭据时的兜底。它确实写了文件,但那不是「送到人手上」。
        return Verdict("G2 投递", False,
                       "channel=local 只写了本地文件,没有任何外部回执 —— 这一幕的要求是送到人手上。",
                       receipt)
    return Verdict("G2 投递", False, f"未知渠道 {channel!r},无法判定。", receipt)


# ── G3 · 部署闸 ───────────────────────────────────────────────────────────────

GH_API = "https://api.github.com"


def _gh(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{GH_API}{path}",
        headers={
            "authorization": f"Bearer {token}",
            "accept": "application/vnd.github+json",
            "user-agent": "parallight-lab-1-b",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def gate_deploy(repo: str | None = None,
                workflow_file: str = "daily.yml",
                *, max_age_hours: int | None = None) -> Verdict:
    """G3:「我部署好了」这四个字没有信息量。要 GitHub 那边真跑过一次。

    判据故意选得很硬:**不看仓库里有没有那个 yml 文件**(文件躺在那儿不等于会跑,
    cron 写错、secrets 没配、Actions 被禁用都会让它一次也不跑),
    只看 **workflow_runs 里有没有一次 conclusion=success 的真实运行**。

    「配置存在」和「它真的跑过」之间隔着一整个部署失败的世界。
    """
    if max_age_hours is None:
        max_age_hours = int(_cfg("deploy_max_age_hours", 48))
    repo = repo or os.environ.get("BROADCAST_REPO", "")
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not repo:
        return Verdict("G3 部署", False, "没设 BROADCAST_REPO(形如 你的用户名/仓库名),无从查起。")
    if not token:
        return Verdict("G3 部署", False, "没设 GITHUB_PERSONAL_ACCESS_TOKEN,查不了 Actions 运行记录。")

    try:
        data = _gh(f"/repos/{repo}/actions/workflows/{workflow_file}/runs?per_page=5", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return Verdict("G3 部署", False,
                           f"{repo} 里没有 workflow {workflow_file} —— 仓库/文件名对不上,或还没推上去。")
        return Verdict("G3 部署", False, f"GitHub API {e.code} —— token 权限够吗(需要 actions:read)?")
    except Exception as e:  # noqa: BLE001
        return Verdict("G3 部署", False, f"查 GitHub 失败:{type(e).__name__}: {e}")

    runs = data.get("workflow_runs", [])
    if not runs:
        return Verdict("G3 部署", False,
                       f"{workflow_file} 存在,但**一次都没跑过**。文件躺在仓库里不等于部署好了 —— "
                       "去 Actions 页点一次 Run workflow,或等 cron 到点。")

    ok_runs = [r for r in runs if r.get("conclusion") == "success"]
    if not ok_runs:
        newest = runs[0]
        return Verdict("G3 部署", False,
                       f"最近一次运行 conclusion={newest.get('conclusion')} "
                       f"(status={newest.get('status')}) —— 去看日志:{newest.get('html_url')}")

    newest = ok_runs[0]
    import datetime as _dt
    try:
        ts = _dt.datetime.fromisoformat(newest["created_at"].replace("Z", "+00:00"))
        age_h = (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        age_h = 0.0
    ev = {"run_id": newest.get("id"), "url": newest.get("html_url"),
          "created_at": newest.get("created_at"), "age_hours": round(age_h, 1)}
    ledger.record(ledger.KIND_DEPLOY, {"repo": repo, "workflow": workflow_file}, ev)

    if age_h > max_age_hours:
        return Verdict("G3 部署", False,
                       f"最近一次成功运行是 {age_h:.0f} 小时前(>{max_age_hours}h)—— "
                       "曾经跑过,但现在不一定还在跑。", ev)
    return Verdict("G3 部署", True,
                   f"run #{newest.get('id')} success,{age_h:.1f} 小时前 —— {newest.get('html_url')}", ev)


ALL_GATES = (gate_score, gate_delivery, gate_deploy)
