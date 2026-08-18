# Lab 1-B · starter 目录说明

七幕,按顺序跑。每一幕都是一个可以单独运行的程序 —— 跑完再看下一幕。

```bash
python preflight.py          # 0 · 环境自检(30 秒)
python smoke_test.py         # 0 · 接线自检(不联网/不花钱,确认代码本身没散架)
python 01_llm.py             # 1 · LLM 是个纯文本函数
python 02_tools.py           # 2 · 工具协议闭环:停下来的是模型,动手的是你
python 03_agent.py           # 3 · 循环一套 = agent(只给安全工具)
python random_baseline.py    # ↳ 摸地板,不花钱
python 04_train_on_gpu.py    # 4 · 真 A10 上微调 💰
python leaderboard.py --submit   # ↳ 提交 + 看排名(免费,不占 GPU 额度)
python 05_verify.py --fresh  # 5 · 先看三道闸全红,再一道道变绿  ★脊椎
python 06_deliver.py         # 6 · 送到人手上,留下回执
# 7 · 见 07_deploy.md —— 推 GitHub,Actions 当闹钟
```

## 文件地图

```
plk.py              挑战服务客户端(token / GPU / 打分 / 榜单)—— 全 lab 唯一一份
leaderboard.py      看成绩榜(终端版)。--submit 先提交再看。免费
                    网页版:/lab/lab-1-b-result,每 5 秒自动刷新
gpurun.py           跑一次 GPU 实验的完整编排(开机→上传→跑→取产物→**必停机**)
train.py            ← 你(和 agent)主要改这个。搜 # TUNE 找可调点
config.yaml         投递渠道 / 闸的容差。**凭据不在这里**
.env                凭据。已被 .gitignore 挡掉

agent/
  llm.py            一层薄封装:调用大模型就是一个 HTTP POST
  loop.py           ReAct 循环,不到 60 行 —— agent 的全部
  trace.py          把每一轮打印出来(💭 想法 / 🔧 工具 / stop_reason / token)
  tools/
    __init__.py     ★ 先读这个。SAFE_TOOLS vs COSTLY_TOOLS 的分组是有意的
    gpu.py          会花真钱的两个工具
    report.py       会往外发东西的工具(注意:schema 里没有收件人字段)
    list_files.py / write_file.py / run_python.py / run_shell.py

verify/             ★ 这个 lab 的脊椎
  ledger.py         证据账本(append-only JSONL)
  gates.py          三道闸 + 三条闸设计纪律

deliver/
  mailer.py         Gmail SMTP。手写 MAIL/RCPT/DATA —— 为了拿到服务器那句回执
  feishu.py         飞书机器人:一个 POST + 一段 JSON
  __init__.py       渠道分发

deploy/daily.yml    GitHub Actions 模板(第 7 幕复制到你自己的仓库)
autopilot.py        无人值守入口。默认不碰 GPU —— 别让定时器有权花钱
run/                跑出来的东西。只有 evidence.jsonl 该进 git
```

## 💰 关于钱

- 每人 **$30** GPU 额度,按分钟计费,用完即停;全局 $400 封顶。
- 一次完整微调 **10–40 分钟**。跑之前先回答:*这一轮我想验证什么?*
- `gpurun.py` 用 `try/finally` 保证跑完就停机 —— 你自己写编排时也照做。
  忘停一台 A10 一晚上就是几十刀。

## 荣誉制

测试集标签在服务端,不在这台机器上。别去网上翻 FGVC-Aircraft 的测试标签 ——
那样刷出来的分只证明你会搜索,不证明你会微调,而且会让第 5 幕整幕失去意义。

## 卡住了

直接问 Mentor。带上你跑的命令 + 完整报错,别只说「跑不通」。
