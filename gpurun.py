"""跑一次 GPU 实验的完整编排 —— 开机 → 上传 → 后台跑 → 轮询 → 取产物 → 关机。

抽成一个函数,因为有三个调用方要用它,而且必须是同一条路径:
  · 你手动跑(04_train_on_gpu.py)
  · agent 自己跑(agent/tools/gpu.py 里的 run_gpu_experiment 工具)
  · 无人值守跑(autopilot.py,GitHub Actions 每天叫醒它)

「同一条路径」不是洁癖:第 5 幕的闸要拿 agent 跑出来的 predictions 去服务端复算。
如果 agent 走的是另一条代码路径,复算出来的分对不上,你分不清是 agent 撒谎还是两条
路径本来就不一样。**要让证据说话,先让路径唯一。**

⚠️ 钱:GPU 按分钟计费,每人 $30 额度。这个函数用 try/finally 保证**无论成功失败都停机**。
   你自己写别的编排时也照做 —— 忘停一台 A10 一晚上就是几十刀。

## 停机是两层,不是一层

  ① **客户端 finally**(下面这个函数):成功 / 抛错 / 训练超时,三条出口都调 gpu_stop。
  ② **服务端 reaper**:每 5 分钟扫一次,闲置超过 ~10 分钟的实例直接终止并结算。

第 ② 层是兜底,专治第 ① 层管不到的情况 —— 进程被 SIGKILL、你直接关了窗口、网断。
`finally` 挡不住 SIGKILL,所以光有第 ① 层是不够的。

## ⚠️ 但第 ② 层有个反噬,自己写编排时必踩

reaper 判「闲置」看的是 **last_active**,而 last_active 只被这几个调用刷新:
`gpu/status`、`gpu/logs`、`gpu/run`、`gpu/upload`、`gpu/fetch`。

也就是说:**训练在 GPU 上跑得再热闹,服务端也不知道。它只看你有没有来说过话。**

下面这个函数每 20 秒轮询一次 status + logs,所以在 40 分钟的训练里一直是「活跃」的。
但如果你自己写成「启动后 sleep(2400),然后回来取结果」——
**你的 GPU 会在第 10 分钟被 reaper 杀掉**,而你看到的现象是「训练莫名其妙没了」。

轮询在这里不只是为了给你看进度,它同时是**心跳**。别把它优化掉。
"""
from __future__ import annotations

import json
import time
from typing import Callable

import plk

DONE_MARKER = "=== TRAINING DONE ==="

REMOTE_TRAIN_PATH = "/home/ubuntu/train.py"
REMOTE_PRED_PATH = "/home/ubuntu/predictions.json"
REMOTE_REPORT_PATH = "/home/ubuntu/report.json"


def _noop(msg: str) -> None:
    print(msg)


def wait_ready(token: str, log: Callable[[str], None] = _noop, max_wait_s: int = 450) -> float:
    """等 GPU 真的能跑命令(Lambda 真机开机约 3–6 分钟)。返回剩余额度。

    别把 live 当就绪信号:live 只说明沙箱建了、开始计费。
    """
    remaining = 0.0
    deadline = time.monotonic() + max_wait_s
    attempt = 0
    while time.monotonic() < deadline:
        time.sleep(5)
        attempt += 1
        status = plk.gpu_status(token)
        remaining = status.get("remainingUsd", remaining)
        if status.get("ready"):
            log(f"  GPU 已就绪 | 剩余额度 ${remaining:.4f}")
            return remaining
        if attempt % 6 == 0:
            log(f"  仍在开机... ({attempt * 5}s) | 剩余额度 ${remaining:.4f}")
    raise plk.ChallengeError(f"GPU 启动超时({max_wait_s}s)")


def run_experiment(
    train_source: str,
    *,
    token: str | None = None,
    log: Callable[[str], None] = _noop,
    poll_s: int = 20,
    max_train_s: int = 3600,
) -> dict:
    """上传一份 train.py 源码到 GPU 跑完,取回预测 + 自报报告。

    返回 {"predictions": [int], "self_report": dict|None, "log_tail": str, "remainingUsd": float}

    注意返回里叫 **self_report** 不叫 result —— 它是训练脚本**自己说**的话,
    在第 5 幕过闸之前,它不算数。
    """
    token = token or plk.require_token()
    sandbox_id = None
    remaining = 0.0
    try:
        log("[1/5] 申请 GPU 沙箱 ...")
        start = plk.gpu_start(token)
        if not start.get("ok"):
            reason = start.get("reason", "unknown")
            hint = {
                "budget_exhausted": "你的 $30 GPU 额度已用尽。",
                "global_budget_exhausted": "全局 GPU 预算($400)已达上限,稍后再试。",
                "at_capacity": "GPU 资源当前满载,稍后再试。",
            }.get(reason, f"GPU 启动失败: {reason}")
            raise plk.ChallengeError(hint)
        sandbox_id = start.get("sandboxId")
        remaining = start.get("remainingUsd", 30.0)
        log(f"  沙箱 {sandbox_id} | 剩余额度 ${remaining:.4f}")

        log("[2/5] 等待 GPU 就绪(约 3–6 分钟)...")
        remaining = wait_ready(token, log)

        log("[3/5] 上传 train.py ...")
        up = plk.gpu_upload(REMOTE_TRAIN_PATH, train_source, token)
        if not up.get("ok"):
            raise plk.ChallengeError(f"上传失败: {up.get('reason')}")

        # 不要在 command 里重定向输出:后台 runner 已经把 stdout/stderr 收进
        # .challenge-job.log,gpu/logs 就是 tail 它。再加 `> train.log` 会让轮询
        # 永远看不到 DONE 标记。(一期踩过。)
        log("[4/5] 后台启动训练,开始轮询日志 ...")
        run = plk.gpu_run("cd /home/ubuntu && python3 -u train.py", background=True, token=token)
        if not run.get("ran"):
            raise plk.ChallengeError(f"训练未能启动: {run.get('reason')}")

        log_text = ""
        deadline = time.monotonic() + max_train_s
        while time.monotonic() < deadline:
            time.sleep(poll_s)
            remaining = plk.gpu_status(token).get("remainingUsd", remaining)
            log_text = plk.gpu_logs(token)
            tail = [l for l in log_text.splitlines() if l.strip()][-2:]
            log(f"  ${remaining:.4f} | " + " | ".join(tail))
            if DONE_MARKER in log_text:
                break
        else:
            raise plk.ChallengeError(
                f"训练超时({max_train_s}s 没等到 {DONE_MARKER})。日志尾:\n"
                + "\n".join(log_text.splitlines()[-15:])
            )

        log("[5/5] 拉取产物 ...")
        fetched = plk.gpu_fetch(REMOTE_PRED_PATH, token)
        if not fetched.get("ok"):
            raise plk.ChallengeError(f"拉 predictions.json 失败: {fetched.get('reason')}")
        predictions = json.loads(fetched["content"])

        self_report = None
        try:
            rep = plk.gpu_fetch(REMOTE_REPORT_PATH, token)
            if rep.get("ok"):
                self_report = json.loads(rep["content"])
        except Exception:
            pass  # 自报报告缺失不致命 —— 反正它本来就不算数

        log(f"  拿到 {len(predictions)} 条预测;自报 = {self_report}")
        return {
            "predictions": predictions,
            "self_report": self_report,
            "log_tail": "\n".join(log_text.splitlines()[-40:]),
            "remainingUsd": remaining,
        }

    finally:
        if sandbox_id is not None:
            try:
                stop = plk.gpu_stop(token)
                log(
                    f"[cleanup] GPU 已停 | 本次花费 ${stop.get('spentUsd', '?')} "
                    f"| 剩余 ${stop.get('remainingUsd', '?')}"
                )
            except Exception as e:  # noqa: BLE001
                log(f"[cleanup] ⚠️ 停机失败,去 /lab 面板手动确认!{e}")
