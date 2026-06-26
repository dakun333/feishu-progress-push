"""
进度节流器 —— 把 `claude -p --output-format stream-json` 的事件，
翻译成人类可读的中文进度行，并**节流**推送到飞书，避免刷屏。

节流规则（两者满足其一才推送）：
  1) 进度「类别」发生变化（如 从思考 → 用 Read 工具），立即推（但有最小间隔保护）；
  2) 同一类别持续中，则每隔 throttle_seconds 秒最多推一次。
连续重复的同一句不会重复推。最终回复由 runner 单独发送，不走这里。
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, Optional

# 工具名 → (类别key, 展示文案)。类别相同视为同一阶段。
_TOOL_MAP = {
    "Read": ("read", "📖 正在读取文件"),
    "Glob": ("search", "🔍 正在查找文件"),
    "Grep": ("search", "🔍 正在搜索内容"),
    "Edit": ("edit", "✏️ 正在修改文件"),
    "MultiEdit": ("edit", "✏️ 正在修改文件"),
    "Write": ("edit", "📝 正在写入文件"),
    "NotebookEdit": ("edit", "✏️ 正在编辑 Notebook"),
    "Bash": ("exec", "💻 正在执行命令"),
    "PowerShell": ("exec", "💻 正在执行命令"),
    "WebSearch": ("web", "🌐 正在联网搜索"),
    "WebFetch": ("web", "🌐 正在抓取网页"),
    "Task": ("task", "🤝 正在调度子任务"),
    "TodoWrite": ("plan", "🗂️ 正在整理任务清单"),
    "TaskCreate": ("plan", "🗂️ 正在整理任务清单"),
}


class ThrottledProgress:
    """
    用法：
        prog = ThrottledProgress(throttle_seconds, push_coro)
        await prog.on_event(evt_dict)   # 对每个 stream-json 事件调用
    push_coro: async (text:str) -> None，真正把进度发到飞书的回调。
    """

    def __init__(
        self,
        throttle_seconds: float,
        push: Callable[[str], Awaitable[None]],
        *,
        min_interval: float = 1.0,
        announce_start: bool = True,
    ):
        self.throttle_seconds = throttle_seconds
        self.push = push
        self.min_interval = min_interval
        self.announce_start = announce_start

        self._last_push_ts: float = 0.0
        self._last_category: Optional[str] = None
        self._last_text: Optional[str] = None
        self._started = False

    @staticmethod
    def _now() -> float:
        return time.time()

    def _classify(self, evt: dict) -> Optional[tuple[str, str]]:
        """把事件映射为 (类别, 文案)；返回 None 表示该事件不产生进度。"""
        etype = evt.get("type")

        if etype == "system" and evt.get("subtype") == "init":
            return ("start", "🚀 已开始处理…")

        if etype == "assistant":
            content = (evt.get("message") or {}).get("content") or []
            # 优先识别工具调用
            for block in content:
                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    cat, label = _TOOL_MAP.get(name, ("tool", f"🔧 正在使用 {name}"))
                    return (cat, label)
            # 否则是模型在输出文本（思考/组织回复）
            for block in content:
                if block.get("type") == "text" and (block.get("text") or "").strip():
                    return ("think", "🧠 正在思考…")
            return None

        # user 事件通常是工具结果；不单独推，避免噪音
        return None

    async def on_event(self, evt: dict) -> None:
        item = self._classify(evt)
        if not item:
            return
        category, text = item

        # 开始事件：是否播报
        if category == "start":
            if not self.announce_start or self._started:
                self._started = True
                return
            self._started = True
            await self._do_push(category, text)
            return

        now = self._now()
        category_changed = category != self._last_category
        time_ok = (now - self._last_push_ts) >= self.throttle_seconds
        # 类别变化也要尊重最小间隔，避免极短时间连发
        min_ok = (now - self._last_push_ts) >= self.min_interval

        if text == self._last_text and not category_changed:
            # 完全重复，跳过
            return

        if (category_changed and min_ok) or time_ok:
            await self._do_push(category, text)

    async def _do_push(self, category: str, text: str) -> None:
        self._last_push_ts = self._now()
        self._last_category = category
        self._last_text = text
        try:
            await self.push(text)
        except Exception:
            # 推送失败不影响主流程
            pass
