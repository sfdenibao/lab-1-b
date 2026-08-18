"""环境自检 —— 开工前 30 秒。

    python preflight.py

只检查「不满足就一定跑不起来」的东西。投递凭据不在这里检查(第 6 幕才需要),
GPU 额度也不在这里检查(服务端说了算)。
"""
import importlib.util
import os
import sys


def ok(cond, msg: str) -> bool:
    print(("✓ " if cond else "✗ ") + msg)
    return bool(cond)


def main() -> None:
    good = True
    good &= ok(sys.version_info >= (3, 10), f"python {sys.version.split()[0]}(需要 3.10+)")

    for mod in ("anthropic", "dotenv", "yaml", "httpx", "pytest"):
        good &= ok(importlib.util.find_spec(mod) is not None, f"pip 包:{mod}")

    good &= ok(os.path.exists(".env"), ".env 存在(/lab-start 会自动生成;手动跑就 cp .env.example .env)")

    # 身份 token —— 没有它,GPU 和打分器都用不了
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import plk
        tok = plk.find_token()
        good &= ok(bool(tok), f"身份 token(plk_){'*** ' + tok[-4:] if tok else '—— 没找到'}")
    except Exception as e:  # noqa: BLE001
        good &= ok(False, f"plk.py 导入失败:{e}")

    good &= ok(os.path.exists("train.py"), "train.py 在(第 4 幕要上传它)")
    good &= ok(os.path.exists("config.yaml"), "config.yaml 在")

    print("\n" + ("ALL GOOD —— 告诉 Mentor 你准备好了。" if good else "先修掉上面的 ✗。"))
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()
