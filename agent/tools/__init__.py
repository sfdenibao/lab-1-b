"""工具注册表:ALL_TOOLS(给模型看的 schema)+ DISPATCH(name → 你的函数)。

这两个列表并排放在一起,是想让你一眼看见 tool_use 的真相:

    ALL_TOOLS  = 你告诉模型「有这些能力」          ← 一堆 JSON,进 context,计价
    DISPATCH   = 模型点名之后,**你的代码**去执行   ← 普通 Python 函数

模型从来没有「使用」过工具。它只是在输出里说了一句「我要 run_gpu_experiment,
参数是这些」,然后停下(stop_reason=tool_use)。真正开 GPU、真正花钱的,是
loop.py 里那行 `dispatch[tu.name](**tu.input)` —— 你写的。

所以「限制 agent 能做什么」从来不是靠 prompt 里求它,是靠这张表里不放那个函数。

分两组是刻意的:
  SAFE_TOOLS  —— 只碰本地文件系统,跑错了重来就行
  COSTLY_TOOLS —— 花钱(GPU)或对外(发信),每一个都该让你犹豫一下
"""
from agent.tools.gpu import (
    GET_PROBLEM_TOOL,
    LEADERBOARD_TOOL,
    RUN_EXPERIMENT_TOOL,
    SUBMIT_TOOL,
    get_problem,
    run_gpu_experiment,
    submit_predictions,
    view_leaderboard,
)
from agent.tools.list_files import LIST_FILES_TOOL, list_files
from agent.tools.report import SEND_REPORT_TOOL, send_report
from agent.tools.run_python import RUN_PYTHON_TOOL, run_python
from agent.tools.run_shell import RUN_SHELL_TOOL, run_shell
from agent.tools.write_file import WRITE_FILE_TOOL, write_file

SAFE_TOOLS = [
    LIST_FILES_TOOL,
    WRITE_FILE_TOOL,
    RUN_PYTHON_TOOL,
    RUN_SHELL_TOOL,
    GET_PROBLEM_TOOL,
    LEADERBOARD_TOOL,   # 免费:看榜不花钱、不占提交额度
]

COSTLY_TOOLS = [
    RUN_EXPERIMENT_TOOL,   # 真 A10,真扣额度
    SUBMIT_TOOL,           # 有每日提交上限
    SEND_REPORT_TOOL,      # 真发到你邮箱/飞书
]

ALL_TOOLS = SAFE_TOOLS + COSTLY_TOOLS

DISPATCH = {
    "list_files": list_files,
    "write_file": write_file,
    "run_python": run_python,
    "run_shell": run_shell,
    "get_problem": get_problem,
    "view_leaderboard": view_leaderboard,
    "run_gpu_experiment": run_gpu_experiment,
    "submit_predictions": submit_predictions,
    "send_report": send_report,
}
