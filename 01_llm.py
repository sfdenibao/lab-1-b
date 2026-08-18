"""第 1 幕 · LLM 是个纯文本函数(kp-01)

跑法:
    python 01_llm.py

这一幕只想让你看清一件事:**调用大模型 = 一个 HTTP POST。**
进去一段文本,出来一段文本。它没有记忆、没有工具、不会上网、不会跑代码。

下面故意问它两个它答不了的问题。它会答 —— 而且答得很顺 —— 这正是重点:
它没有能力说「我不知道」,它只会把话接下去。这个性质会一路贯穿到第 5 幕:
**它报给你的精度,和它编给你的天气,是同一台机器生成的。**
"""
from dotenv import load_dotenv

from agent.llm import DEFAULT_MODEL, complete

load_dotenv()


def show(title: str, prompt: str) -> None:
    msg = complete([{"role": "user", "content": prompt}], model=DEFAULT_MODEL, max_tokens=300)
    text = "".join(b.text for b in msg.content if b.type == "text")
    print(f"\n── {title} ──")
    print(f"问: {prompt}")
    print(f"答: {text.strip()}")
    print(f"   [in/out tokens = {msg.usage.input_tokens}/{msg.usage.output_tokens}"
          f"  stop_reason={msg.stop_reason}]")


def main() -> None:
    show("① 它能答的", "一句话说清什么是迁移学习。")

    show("② 它没有记忆", "我刚才问了你什么?")

    show("③ 它碰不到这台机器", "我这个目录下有哪些文件?")

    show("④ 它给不出真数字", "FGVC-Aircraft 上 resnet18 微调 5 轮的测试集准确率是多少?")

    print("""
────────────────────────────────────────────────────────────
看 ②:它不知道你上一句问了什么 —— 每次 POST 都是全新的,历史得你自己带。
看 ③:它猜了一堆文件名 —— 它碰不到你的磁盘,但它不会因此闭嘴。
看 ④:它给了你一个具体到小数点的数字 —— 你信吗?这个数字和 ③ 里那些文件名
      是同一种东西:接下去最像的词。

第 5 幕整幕都在处理这件事。现在先记住这句:
      **模型说出来的数字,是生成的,不是测出来的。**

下一幕:python 02_tools.py —— 给它一双手。
────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    main()
