"""邮件投递 —— 默认 Gmail SMTP。**重点在拿回执,不在把信发出去。**

一般教程写 SMTP 就是 `s.sendmail(...)` 一行完事。这里故意把最后三步拆开手写:

    MAIL FROM → RCPT TO → DATA

因为 `sendmail()` 会把服务器对 DATA 的那句回复**吞掉**,而那句回复恰恰是这一幕
唯一算数的东西 —— Gmail 会回类似 `2.0.0 OK  1723... - gsmtp`,里面那串是**它的**队列 ID。
这个字符串你编不出来,agent 也编不出来。这才叫回执。

对比一下三种「证明我发了信」的说法,强度天差地别:
    ① agent 说「已发送」                     — 零证据(就是一段生成的文本)
    ② 函数 return True                       — 零证据(还是自己说自己)
    ③ 服务器对 DATA 回的那句 250 + 队列 ID   — 证据(外面给的)

⚠️ 但即便是 ③,它只证明**收下了(transport)**,不证明**进了收件箱(deliverability)**。
   进不进垃圾箱是 SPF/DKIM/发信信誉的事,SMTP 这一层看不见。闸不能声称它没证据的事。

⚠️ Gmail SMTP 不收登录密码:先开两步验证,再生成「应用专用密码」(App Password),
   填到 .env 的 GMAIL_APP_PASSWORD。换别的邮箱就改 SMTP_HOST / SMTP_PORT / SMTP_USER。
"""
from __future__ import annotations

import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid


def push(title: str, markdown: str) -> dict:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = (os.environ.get("GMAIL_ADDRESS") or os.environ.get("SMTP_USER") or "").strip()
    pw = (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASSWORD") or "").strip()
    to = (os.environ.get("MAIL_TO") or user).strip()  # 默认发给自己

    if not (user and pw):
        return {"ok": False, "reason": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD 没配"}

    msg_id = make_msgid(domain=user.split("@")[-1] or "localhost")
    msg = MIMEText(markdown, "plain", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = user
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msg_id

    try:
        with smtplib.SMTP(host, port, timeout=25) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(user, pw)

            code, resp = s.docmd("MAIL", f"FROM:<{user}>")
            if code != 250:
                return {"ok": False, "reason": f"MAIL FROM 被拒 {code}: {resp!r}"}

            code, resp = s.docmd("RCPT", f"TO:<{to}>")
            if code not in (250, 251):
                return {"ok": False, "reason": f"RCPT TO 被拒 {code}: {resp!r}"}

            # data() 负责 DATA / 354 / 正文 / 结束点,并把服务器最后那句回复还给我们。
            code, resp = s.data(msg.as_string())
            if code != 250:
                return {"ok": False, "reason": f"DATA 被拒 {code}: {resp!r}"}

            smtp_response = resp.decode("utf-8", "replace") if isinstance(resp, bytes) else str(resp)

    except Exception as e:  # noqa: BLE001  在大陆本地跑会卡在这里连不上 smtp.gmail.com
        return {"ok": False, "reason": f"SMTP 失败(transport):{type(e).__name__}: {e}"}

    return {
        "ok": True,
        "to": to,
        "message_id": msg_id,          # 我们自己写的头 —— 用来在自己邮箱里搜到这封信
        "smtp_code": code,             # 服务器给的
        "smtp_response": smtp_response,  # 服务器给的队列 ID —— 这条才是 G2 认的证据
    }
