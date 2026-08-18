"""飞书自定义机器人投递 —— slides 第 7 幕的「webhook = URL 即凭据」。

本质就是：**一个 HTTP POST + 一段 JSON**（msg_type 选模板）。和你在 Lab-1 调工具一样朴素。

安全模型（kp-04 必讲）：
  · webhook URL 里那段 token **本身就是凭据**——谁拿到谁能往群里发。放 .env，绝不进 git/日志/截图。
  · 限流：单机器人 100 次/分钟、5 次/秒（企业微信只有 20/分）。批量通知要自己合并。
  · 「发出去」≠「进收件箱」：这是 IM 推送（基本即达）；邮件还要过 ISP 反垃圾。
  · 渠道选择（kp-04）：在大陆的同学用飞书最顺（app 即时收到）；在国外用 Gmail 更方便。
    注意反向坑：从**境外**服务器/沙箱 POST 飞书 webhook 偶有连接抖动——发不出去时看返回、用 local 兜底。
"""
import os
import time
import hmac
import hashlib
import base64
import httpx


def _sign(secret: str, ts: str) -> str:
    # 飞书签名：把 `timestamp\nsecret` 当作 HMAC-SHA256 的 *密钥*，对空消息签名，再 Base64。
    # （不同语言示例写法略有差异，以官方对应语言 demo 为准；timestamp 不得超过 1 小时。）
    s = f"{ts}\n{secret}"
    digest = hmac.new(s.encode("utf-8"), b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def push(title: str, markdown: str) -> dict:
    """把一条『今日播报』推到飞书群。返回 {ok, status, resp}。"""
    url = (os.environ.get("FEISHU_WEBHOOK_URL") or "").strip()
    if not url:
        return {"ok": False, "reason": "FEISHU_WEBHOOK_URL 没配 —— 用 config 的 channel: local 兜底（只写本地 digest.md）"}

    # text 模板最稳、必达；标题放进正文（若机器人开了「关键词」安全，标题也能当关键词命中）。
    text = f"{title}\n\n{markdown}"
    payload = {"msg_type": "text", "content": {"text": text}}

    # 若开了「签名校验」安全模式，补上 timestamp + sign。
    secret = (os.environ.get("FEISHU_WEBHOOK_SECRET") or "").strip()
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = _sign(secret, ts)

    try:
        r = httpx.post(url, json=payload, timeout=20)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except Exception as e:  # 沙箱在境外，偶发连接抖动；定位「没发出去」
        return {"ok": False, "reason": f"请求失败（transport）: {e}"}
    # 飞书成功返回 code:0；否则 data 里有 code/msg 帮你定位「发了没进群」。
    # code 单独平铺出来 —— 第 5 幕的 G2 闸认的就是它（飞书给的，不是我们自己说的）。
    code = data.get("code")
    return {
        "ok": code == 0,
        "code": code,
        "status": r.status_code,
        "resp": data,
        "reason": None if code == 0 else f"飞书 code={code} msg={data.get('msg')!r}",
    }


# 💡 想要更漂亮的卡片（飞书最富的形态 interactive）？把上面的 payload 换成：
#   payload = {"msg_type": "interactive", "card": {"schema": "2.0",
#       "header": {"title": {"tag": "plain_text", "content": title}},
#       "body": {"elements": [{"tag": "markdown", "content": markdown}]}}}
# 卡片 schema 偶有版本差异，先用 text 跑通、再升级——这本身就是一道好的 challenge。
