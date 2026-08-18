"""第 2 幕 · 工具协议闭环:模型只是「请求」,执行在你的代码里(kp-02)

跑法:
    python 02_tools.py

第 1 幕里它猜了目录内容。这一幕我们给它一个 list_files 工具,再问同一个问题。

**别急着看结果,先看这个循环里的手工步骤。** 这里故意不用 agent/loop.py,
而是把一轮 tool_use 拆开手写,因为「模型自己会用工具」这句话在协议层是假的:

    1. 你在请求里带上 tools=[schema]      ← 工具是一段 JSON,进 context,要花钱
    2. 模型输出一个 tool_use 块,然后停下  ← stop_reason="tool_use"。它停了。
    3. **你的代码**看到这个 stop,去查表,去执行   ← 花钱/删文件的是这一步
    4. 你把结果包成 tool_result 塞回去,再发一次请求  ← tool_use_id 负责配对

第 3 步是整个 agent 安全模型的根:模型没有手,你才是它的手。
你不给它 rm 这个函数,它把 "rm -rf /" 说得再顺也删不掉任何东西。
"""
from dotenv import load_dotenv

from agent.llm import DEFAULT_MODEL, complete
from agent.tools.list_files import LIST_FILES_TOOL, list_files

load_dotenv()

QUESTION = "当前目录下有哪些 .py 文件?列出来。"


def main() -> None:
    messages = [{"role": "user", "content": QUESTION}]

    # ① 带上工具 schema 发第一次
    resp = complete(messages, model=DEFAULT_MODEL, tools=[LIST_FILES_TOOL], max_tokens=800)
    print(f"[第 1 次请求] stop_reason = {resp.stop_reason}")
    for b in resp.content:
        if b.type == "text" and b.text.strip():
            print(f"  💭 {b.text.strip()}")
        elif b.type == "tool_use":
            print(f"  🔧 它请求调用: {b.name}({b.input})   id={b.id}")

    if resp.stop_reason != "tool_use":
        print("\n它这次没要工具。再跑一次;或者想想 description 该怎么写才让它想用。")
        return

    # ② 轮到你干活 —— 模型在这一步是停着的
    messages.append({"role": "assistant", "content": resp.content})
    results = []
    for tu in (b for b in resp.content if b.type == "tool_use"):
        output = list_files(**tu.input)          # ← 真正读磁盘的是这一行
        print(f"\n[你的代码执行了] list_files({tu.input}) →\n{output}")
        results.append({"type": "tool_result", "tool_use_id": tu.id, "content": output})

    # ③ 把结果喂回去,再发一次
    messages.append({"role": "user", "content": results})
    final = complete(messages, model=DEFAULT_MODEL, tools=[LIST_FILES_TOOL], max_tokens=800)
    text = "".join(b.text for b in final.content if b.type == "text")
    print(f"\n[第 2 次请求] stop_reason = {final.stop_reason}")
    print(f"  ✅ {text.strip()}")

    print("""
────────────────────────────────────────────────────────────
对照第 1 幕:同一个问题,这次它答对了。多出来的不是「智能」,是一次磁盘读取。

三件事记住:
  · tool 三件套 = schema(告诉它有什么) + 你的函数(真干活) + tool_result(喂回去)
  · tool_use_id 是配对机制 —— 一轮可以请求多个工具,靠 id 对上号
  · **停下来的是模型,动手的是你。** 所谓「agent 有权限做 X」= 你在 DISPATCH 里
    放了做 X 的那个函数。

下一幕:python 03_agent.py —— 把这个手工循环自动化,它就成 agent 了。
────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    main()
