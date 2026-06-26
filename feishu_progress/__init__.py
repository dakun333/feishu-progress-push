"""
feishu-progress-push
=====================

把长耗时的 Claude Code (`claude -p`) 任务的执行过程，以**节流**的方式实时推送到飞书聊天，
让用户在飞书里就能看到「正在思考 / 正在读文件 / 正在执行命令…」，以及任务的
执行 / 完成 / 超时 / 异常状态。即插即用，配置极简。

最常用的入口：

    import asyncio
    from feishu_progress import Config, run_claude_with_progress, format_status

    cfg = Config.from_env()          # 从环境变量 / .env 读取配置

    async def main():
        result = await run_claude_with_progress(
            prompt="帮我分析这段代码",
            chat_id="oc_xxxxxxxx",    # 飞书会话 id
            config=cfg,
        )
        print(result.text)           # 最终回复（最终回复始终照常返回，不受节流影响）
        print(format_status("oc_xxxxxxxx"))   # 人类可读的状态

详见 README.md。
"""

from .config import Config
from .notifier import FeishuNotifier
from .status import (
    ProcState,
    get_status,
    format_status,
    all_status,
)
from .progress import ThrottledProgress
from .runner import run_claude_with_progress, ClaudeResult

__all__ = [
    "Config",
    "FeishuNotifier",
    "ProcState",
    "get_status",
    "format_status",
    "all_status",
    "ThrottledProgress",
    "run_claude_with_progress",
    "ClaudeResult",
]

__version__ = "0.1.0"
