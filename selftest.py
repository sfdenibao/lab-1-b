"""自测模式(仅老师/QA 用):对上口令 → 进入「全 QA 通关」。普通学员走 lab 用不到这个。
  python selftest.py <口令>
对上(服务端校验通过)→ mentor 进入全 QA 通关:直接给答案/解法、checkpoint 一律放行、可跳任意步,
目标=最快把整条 lab 端到端验一遍。对不上 → 啥也不解锁。口令只你知道,服务端校验。"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("PARALLIGHT_LAB_BASE", "https://www.parallight.ai").rstrip("/")


def find_token():
    t = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("PARALLIGHT_API_KEY")
    if t and t.startswith("plk_"):
        return t
    for p in (os.path.expanduser("~/.parallight/auth.json"), os.path.expanduser("~/.claude/settings.json")):
        try:
            d = json.load(open(p))
            for k in ("proxy_token", "lab_gateway_token", "ANTHROPIC_AUTH_TOKEN"):
                v = d.get(k) or (d.get("env", {}) or {}).get(k)
                if isinstance(v, str) and v.startswith("plk_"):
                    return v
        except Exception:
            pass
    return None


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit("用法: python selftest.py <口令>")
    token = find_token()
    if not token:
        sys.exit("没找到身份 token(plk_)。在线 lab 里应自动有。")

    req = urllib.request.Request(
        f"{BASE}/lab/api/lab/selftest",
        data=json.dumps({"passphrase": sys.argv[1]}).encode(),
        method="POST",
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = json.loads(resp.read()).get("unlocked") is True
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("❌ 口令错误,未解锁。")
            return
        if e.code == 503:
            print("❌ 自测口令未配置(后端没设 LAB_SELFTEST_PASSPHRASE)。")
            return
        print(f"❌ 解锁失败({e.code})。")
        return

    if ok:
        print("✅ 自测模式已解锁(全 QA 通关)。")
        print("   mentor 现在会:直接给每步答案/解法、checkpoint 一律放行、可跳到任意步/任意幕。")
    else:
        print("❌ 未解锁。")


if __name__ == "__main__":
    main()
