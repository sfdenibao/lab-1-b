# 第 7 幕 · 让它常驻:推到 GitHub,让 Actions 当闹钟(kp-07)

前六幕结束时你有一个能跑通全程的东西 —— 但它只在你按回车的时候活着。
这一幕把它变成一个**你关掉电脑之后还在跑**的东西。

三层,别搞混:

| 层 | 是谁 | 管什么 |
|---|---|---|
| 闹钟 | GitHub Actions `schedule` | **WHEN** —— 什么时候叫醒 |
| agent | `autopilot.py` | **WHAT** —— 醒来干什么 |
| 手 | SMTP / GitHub API / 挑战服务 | **HOW** —— 真去碰外部世界 |

一个常见误解是「让 MCP server 自己定时跑」。MCP server 是**被动**的工具提供方,
它没有时钟,只在被调用时才动。你的 agent 也一样。**闹钟必须在外面。**

---

## Step 1 · 建仓库并推上去

用第 3 幕那个 agent 配合 GitHub MCP 来做(`.mcp.json` 里已经配好了),
或者你自己手动 —— 这一步不是重点,重点是推上去之后的验收。

要推的东西:

```
your-automl-repo/
  autopilot.py
  plk.py  gpurun.py  train.py  config.yaml  requirements.txt
  agent/  deliver/  verify/
  .github/workflows/daily.yml     ← 从 deploy/daily.yml 复制过去
```

**绝对不要推的**:`.env`(凭据)、`run/predictions.json`(几千行没意义)。
`.gitignore` 已经挡了,但推之前自己 `git status` 看一眼 ——
凭据一旦进了 git 历史,删文件是没用的,得改密码。

---

## Step 2 · 配 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret:

| Secret | 值 |
|---|---|
| `PARALLIGHT_API_KEY` | 你的 `plk_...`(在线 lab 里 `/lab-start` 注入过,或看 `.env`) |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` / `MAIL_TO` | 走邮件渠道时 |
| `FEISHU_WEBHOOK_URL` | 走飞书渠道时 |

> Secret 名字**不能以 `GITHUB_` 开头**,这是 GitHub 的保留前缀。要放 GitHub token
> 就叫 `GH_LAB_TOKEN` 之类。

---

## Step 3 · 手动触发一次(**必须**)

Actions 页 → daily-automl → Run workflow → **train 保持 false** → Run。

为什么必须手动跑一次:cron 到点触发一次要等到明天,而错误往往在第一次才暴露 ——
secret 名字打错、`requirements.txt` 少一个包、python 版本对不上。
等到明天早上发现没收到日报,你已经浪费一天了。

---

## Step 4 · 过 G3 闸

```bash
export BROADCAST_REPO=你的用户名/仓库名
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...    # 需要 actions:read 权限
python 05_verify.py --only G3
```

G3 故意**不看**仓库里有没有 `daily.yml`。文件躺在那儿不等于它会跑 ——
cron 语法写错、Actions 被组织策略禁用、workflow 文件不在默认分支上、
仓库 60 天没提交被自动停用,每一种都会让它一次也不跑,而文件一直好好地躺着。

G3 只认一件事:**`workflow_runs` 里有一次 `conclusion: success`。**

「配置存在」和「它真的跑过」之间,隔着一整个部署失败的世界。

---

## ⚠️ 关于钱:为什么定时任务不许训练

`daily.yml` 里那行:

```yaml
AUTOPILOT_ALLOW_GPU: ${{ github.event.inputs.train == 'true' && '1' || '0' }}
```

定时触发时 `inputs.train` 是空的 → 这个变量是 `'0'` → `autopilot.py` 里的第二道闸
直接退出。**定时那条路径在结构上就没有启动 GPU 的能力。**

这不是小心,这是设计。一个每天自动扣钱的 workflow,只要有一次 cron 写错
(`* * * * *` 少写几个星号 = 每分钟一次),你的额度一个小时就没了。

同一条原则在这个 lab 里出现了三次,值得连起来看:

1. 第 2 幕:限制 agent 能做什么 = **不给它那个函数**(不是在 prompt 里求它)
2. 第 6 幕:防止发错收件人 = **参数里没有收件人这个字段**(不是叮嘱它别乱发)
3. 第 7 幕:防止定时器烧钱 = **那条路径拿不到 GPU 能力**(不是加个预算检查)

三次都是同一句话:**防线在执行层,不在措辞层。**

---

## 交付标准

跑 `python 05_verify.py`,三道闸全绿,然后把 `run/evidence.jsonl` 交出来。

不要交「我部署好了」。那四个字没有信息量。
