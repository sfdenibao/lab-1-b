"""让 agent 能碰真 GPU 的两个工具 —— 第 4 幕。

前面几幕的工具(读目录、写文件、跑 python)代价都很小,跑错了大不了重来。
这两个不一样:**它们会花你的钱**。一台 A10 按分钟计费,每人 $30 额度。

所以这里体现两条工具设计纪律,值得单独看:

**① description 就是 prompt。**
   模型选不选这个工具、怎么填参数,全靠这段英文。它不是文档,是你写给模型的指令。
   下面的 description 里明确写了「每次调用花几美元」「先跑 estimate 再跑真的」——
   这些话是**为了改变模型的行为**才写的,不是为了给人看。

**② 结果要控体积。**
   训练日志几万 token,原样塞回 context 会让后面每一轮都为它付一次钱(二次成本)。
   工具只回传日志的尾巴 + 落盘路径,让 agent 想看细节时自己去读文件。
   context 是工作台,不是仓库。
"""
from __future__ import annotations

import json
import os

import gpurun
import plk

RUN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "run"
)

# ── 工具 1:看题 ──────────────────────────────────────────────────────────────

GET_PROBLEM_TOOL: dict = {
    "name": "get_problem",
    "description": (
        "Get the FGVC-Aircraft challenge metadata: number of classes, number of test "
        "images, and the two published reference scores (frozen-backbone baseline and "
        "full-finetune reference). FREE — costs no GPU money. Call this first so you "
        "know what score is worth aiming for. Returns 'Error: ...' on failure."
    ),
    "input_schema": {"type": "object", "properties": {}},
}


def get_problem() -> str:
    try:
        p = plk.problem()
    except plk.ChallengeError as e:
        return f"Error: {e}"
    return json.dumps(p, ensure_ascii=False)


# ── 工具 2:跑一次真实验 ───────────────────────────────────────────────────────

RUN_EXPERIMENT_TOOL: dict = {
    "name": "run_gpu_experiment",
    "description": (
        "Run ONE training experiment on a real A10 GPU: boots a sandbox, uploads the "
        "given train.py source, trains, downloads predictions, and ALWAYS shuts the GPU "
        "down afterwards.\n"
        "COST WARNING: each call bills real money against a $30 per-learner budget and "
        "takes 10-40 minutes. Do NOT call it to 'check if something works' — change one "
        "lever at a time and think about what you expect BEFORE each call.\n"
        "The train_source you pass must write /home/ubuntu/predictions.json and print "
        "'=== TRAINING DONE ==='. Start from the local train.py and edit the # TUNE lines.\n"
        "Returns a JSON summary with the SELF-REPORTED accuracy and where predictions "
        "were saved. The self-reported number is NOT a score — it has not been verified "
        "against the held-out scorer. Use submit_predictions for a real score.\n"
        "Returns 'Error: ...' on failure."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "train_source": {
                "type": "string",
                "description": "Full Python source of the training script to run on the GPU.",
            },
            "note": {
                "type": "string",
                "description": "One line: what you changed and what you expect. Recorded with the run.",
            },
        },
        "required": ["train_source", "note"],
    },
}


def run_gpu_experiment(train_source: str, note: str = "") -> str:
    os.makedirs(RUN_DIR, exist_ok=True)
    lines: list[str] = []
    try:
        result = gpurun.run_experiment(train_source, log=lambda m: (print(m), lines.append(m)))
    except plk.ChallengeError as e:
        return f"Error: {e}"

    pred_path = os.path.join(RUN_DIR, "predictions.json")
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(result["predictions"], f)

    report = dict(result["self_report"] or {})
    report["note"] = note
    report_path = os.path.join(RUN_DIR, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)

    # 日志落盘,只把尾巴回给 context —— 别让几万 token 的训练日志进对话。
    with open(os.path.join(RUN_DIR, "train.log"), "w", encoding="utf-8") as f:
        f.write(result["log_tail"])

    return json.dumps(
        {
            "self_reported": report.get("claimed_accuracy"),
            "warning": "self_reported is UNVERIFIED — it is whatever the training script said.",
            "n_predictions": len(result["predictions"]),
            "predictions_saved_to": pred_path,
            "report_saved_to": report_path,
            "log_tail_saved_to": os.path.join(RUN_DIR, "train.log"),
            "remainingUsd": result["remainingUsd"],
        },
        ensure_ascii=False,
    )


# ── 工具 3:去换一个真分 ───────────────────────────────────────────────────────

SUBMIT_TOOL: dict = {
    "name": "submit_predictions",
    "description": (
        "Submit the predictions from the most recent experiment to the SERVER-SIDE "
        "held-out scorer and get back the only score that counts. The test labels live "
        "on the server, not on this machine — you cannot compute this number yourself, "
        "you can only trade predictions for it.\n"
        "There is a daily submission cap, so submit when you have something to submit, "
        "not to poke at it. Returns 'Error: ...' on failure."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "predictions_path": {
                "type": "string",
                "description": "Path to the predictions JSON produced by run_gpu_experiment.",
            }
        },
        "required": ["predictions_path"],
    },
}


def submit_predictions(predictions_path: str) -> str:
    try:
        with open(predictions_path, encoding="utf-8") as f:
            preds = json.load(f)
    except Exception as e:  # noqa: BLE001
        return f"Error: cannot read {predictions_path}: {type(e).__name__}: {e}"
    try:
        resp = plk.submit(preds)
    except plk.ChallengeError as e:
        return f"Error: {e}"
    return json.dumps(resp, ensure_ascii=False)


# ── 工具 4:看榜 ──────────────────────────────────────────────────────────────

LEADERBOARD_TOOL: dict = {
    "name": "view_leaderboard",
    "description": (
        "Read the public leaderboard: everyone's best server-verified score, your own rank, "
        "and how much GPU budget each person burned to get there. FREE — no GPU cost, no "
        "submission quota.\n"
        "Use it to decide whether another expensive run is worth it: if you are already above "
        "the full-finetune reference and near the top, the marginal point costs more than it "
        "is worth. Returns 'Error: ...' on failure."
    ),
    "input_schema": {"type": "object", "properties": {}},
}


def view_leaderboard() -> str:
    try:
        d = plk.leaderboard()
    except plk.ChallengeError as e:
        return f"Error: {e}"
    # 只回传决策需要的:前 5 名 + 你自己 + 参考线。整张榜(可能 200 行)不进 context。
    return json.dumps(
        {
            "top5": [
                {"rank": r["rank"], "score": r["score"], "spentUsd": r["spentUsd"]}
                for r in d.get("board", [])[:5]
            ],
            "you": d.get("you"),
            "reference": d.get("reference"),
            "baseline": d.get("baseline"),
            "totalEntrants": len(d.get("board", [])),
        },
        ensure_ascii=False,
    )
