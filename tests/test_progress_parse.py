"""
离线自检：用样例 stream-json 事件验证进度分类、节流、状态格式化。
不调用飞书、不调用 claude CLI。

运行：python tests/test_progress_parse.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feishu_progress.progress import ThrottledProgress, _TOOL_MAP
from feishu_progress import status as st


def _assistant_tool(name):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": {}}]}}


def _assistant_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


INIT = {"type": "system", "subtype": "init", "session_id": "abcd1234", "model": "x"}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "result": "done", "duration_ms": 1234}


async def test_category_change_pushes_immediately():
    pushed = []
    prog = ThrottledProgress(throttle_seconds=999, push=lambda t: pushed.append(t) or _noop(),
                             min_interval=0.0)
    # 不同类别应各推一次（throttle 很大也不挡类别变化）
    await prog.on_event(INIT)
    await prog.on_event(_assistant_text("思考中"))      # think
    await prog.on_event(_assistant_tool("Read"))         # read
    await prog.on_event(_assistant_tool("Bash"))         # exec
    assert pushed == ["🚀 已开始处理…", "🧠 正在思考…", "📖 正在读取文件", "💻 正在执行命令"], pushed
    print("✓ 类别变化即时推送 & 文案映射正确")


async def test_same_category_throttled():
    pushed = []
    prog = ThrottledProgress(throttle_seconds=999, push=lambda t: pushed.append(t) or _noop(),
                             min_interval=0.0, announce_start=False)
    await prog.on_event(_assistant_tool("Read"))
    await prog.on_event(_assistant_tool("Read"))   # 同类别同文案，且 throttle 未到 → 不推
    await prog.on_event(_assistant_tool("Glob"))   # 仍是 search? Read=read, Glob=search → 类别变 → 推
    assert pushed == ["📖 正在读取文件", "🔍 正在查找文件"], pushed
    print("✓ 同类别重复被节流，类别变化才推")


async def test_throttle_by_time():
    pushed = []
    prog = ThrottledProgress(throttle_seconds=0.05, push=lambda t: pushed.append(t) or _noop(),
                             min_interval=0.0, announce_start=False)
    await prog.on_event(_assistant_text("a"))   # think 推一次
    await prog.on_event(_assistant_text("a"))   # 完全重复 → 跳过
    assert pushed == ["🧠 正在思考…"], pushed
    print("✓ 时间节流 + 重复跳过")


def test_tool_map_covers_common():
    for t in ("Read", "Edit", "Write", "Bash", "Grep", "WebSearch", "Task"):
        assert t in _TOOL_MAP, t
    print("✓ 常用工具映射齐全")


def test_status_lifecycle():
    cid = "oc_test"
    st.mark_running(cid, pid=111, session_id="abcd1234ef", task="分析代码")
    s = st.get_status(cid)
    assert s["state"] == st.ProcState.RUNNING and s["pid"] == 111
    assert "执行中" in st.format_status(cid)

    st.update_progress(cid, "💻 正在执行命令")
    assert "正在执行命令" in st.format_status(cid)

    st.mark_done(cid, "这是回复")
    assert "已完成" in st.format_status(cid)

    st.mark_running(cid, pid=222, session_id="x", task="t")
    st.mark_timeout(cid)
    assert "超时" in st.format_status(cid)

    st.mark_running(cid, pid=333, session_id="x", task="t")
    st.mark_error(cid, "boom")
    assert "异常" in st.format_status(cid) and "boom" in st.format_status(cid)

    assert "空闲" in st.format_status("oc_never_seen")
    print("✓ 状态生命周期 & 格式化正确")


async def _noop():
    return None


async def main():
    await test_category_change_pushes_immediately()
    await test_same_category_throttled()
    await test_throttle_by_time()
    test_tool_map_covers_common()
    test_status_lifecycle()
    print("\n全部自检通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
