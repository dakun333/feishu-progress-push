"""
核心 runner —— 调用 `claude -p --output-format stream-json --verbose`，
边读事件流边节流推送进度到飞书，跟踪状态，超时按 PID 结束进程树，返回最终回复。

设计要点：
- 用户消息走 stdin 传入，规避 Windows 命令行中文编码问题。
- 仅按 **PID** 结束本次任务的进程树（Windows: taskkill /PID /T /F），
  **绝不**按进程名 (claude.exe / node.exe) 群杀——否则会误杀用户其它 Claude 会话。
- 最终回复始终完整返回，不受进度节流影响。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from . import status as st
from .config import Config
from .notifier import FeishuNotifier
from .progress import ThrottledProgress

logger = logging.getLogger("feishu_progress")


@dataclass
class ClaudeResult:
    text: str                    # 最终回复文本
    state: str                   # ProcState 值：done / timeout / error
    session_id: str              # 本次使用/创建的 session id
    is_error: bool = False
    error: str = ""
    duration_ms: int = 0


def _kill_proc_tree(proc) -> None:
    """只结束本次子进程及其子进程树（按 PID）。绝不按进程名群杀。"""
    if proc is None or proc.returncode is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            # POSIX：尝试杀进程组（需 start_new_session=True 启动），否则退化为杀单进程
            try:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        logger.info(f"🔪 已结束本次任务进程树 pid={proc.pid}")
    except Exception as e:
        logger.warning(f"结束进程 pid={getattr(proc, 'pid', '?')} 失败: {e}")
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def _build_cmd(config: Config, session_id: str, is_new: bool) -> list[str]:
    cmd = [config.claude_cli_path]
    for d in config.claude_add_dirs:
        d = d.strip()
        if d and os.path.isdir(d):
            cmd.extend(["--add-dir", d])
    cmd.append("-p")
    cmd.extend(["--output-format", "stream-json", "--verbose"])
    if is_new:
        cmd.extend(["--session-id", session_id])
    else:
        cmd.extend(["--resume", session_id])
    cmd.extend(["--permission-mode", "bypassPermissions"])
    if config.skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if config.claude_model:
        cmd.extend(["--model", config.claude_model])
    return cmd


async def run_claude_with_progress(
    prompt: str,
    chat_id: str,
    config: Config,
    *,
    session_id: Optional[str] = None,
    is_new: bool = True,
    notifier: Optional[FeishuNotifier] = None,
    push_progress: bool = True,
    on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
) -> ClaudeResult:
    """
    跑一次 Claude 任务并把进度节流推送到飞书。

    参数：
      prompt        用户消息
      chat_id       飞书会话 id（进度/状态都按它聚合）
      config        Config 实例
      session_id    可选；不传则新建一个 uuid（is_new 默认 True）
      is_new        True=用 --session-id 新建；False=用 --resume 续接
      notifier      可选；不传则用 config 现造一个
      push_progress 是否把进度推到飞书（False 则只更新状态/调 on_progress）
      on_progress   可选回调，每条进度也会回调一份（方便自定义处理/日志）

    返回 ClaudeResult。最终回复在 result.text。
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
        is_new = True

    if notifier is None:
        notifier = FeishuNotifier(config)

    st.mark_running(chat_id, pid=None, session_id=session_id, task=prompt)

    async def _push(text: str) -> None:
        st.update_progress(chat_id, text)
        if on_progress:
            await on_progress(text)
        if push_progress:
            await notifier.send_text(chat_id, text)

    prog = ThrottledProgress(config.throttle_seconds, _push)

    cmd = _build_cmd(config, session_id, is_new)
    logger.info(f"▶️  claude | chat={chat_id} | session={session_id[:8]} | new={is_new}")

    proc = None
    final_text_blocks: list[str] = []
    result_evt: Optional[dict] = None

    async def _drive() -> None:
        nonlocal result_evt
        # 写入 prompt 后关闭 stdin
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            # 收集 assistant 文本，作为最终回复兜底
            if evt.get("type") == "assistant":
                for block in (evt.get("message") or {}).get("content") or []:
                    if block.get("type") == "text" and block.get("text"):
                        final_text_blocks.append(block["text"])

            if evt.get("type") == "result":
                result_evt = evt

            await prog.on_event(evt)

        await proc.wait()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config.claude_work_dir or None,
        )
        st.update_pid(chat_id, proc.pid)

        await asyncio.wait_for(_drive(), timeout=config.timeout)

    except asyncio.TimeoutError:
        logger.error(f"⏰ 超时 ({config.timeout}s) | chat={chat_id} | 结束 pid={getattr(proc,'pid','?')}")
        _kill_proc_tree(proc)
        st.mark_timeout(chat_id)
        return ClaudeResult(
            text=f"⏰ 处理超时（{config.timeout} 秒），任务已被终止，请简化后重试。",
            state=st.ProcState.TIMEOUT.value,
            session_id=session_id,
            is_error=True,
            error="timeout",
        )
    except FileNotFoundError:
        st.mark_error(chat_id, f"找不到 claude CLI: {config.claude_cli_path}")
        return ClaudeResult(
            text="❌ 找不到 Claude CLI，请检查 CLAUDE_CLI_PATH 配置。",
            state=st.ProcState.ERROR.value, session_id=session_id,
            is_error=True, error="claude cli not found",
        )
    except Exception as e:
        logger.exception(f"运行异常: {e}")
        _kill_proc_tree(proc)
        st.mark_error(chat_id, str(e))
        return ClaudeResult(
            text="❌ 处理出现异常，请稍后重试。",
            state=st.ProcState.ERROR.value, session_id=session_id,
            is_error=True, error=str(e),
        )

    # ── 正常结束：从 result 事件提取最终文本 ──
    duration = 0
    if result_evt is not None:
        duration = int(result_evt.get("duration_ms") or 0)
        is_err = bool(result_evt.get("is_error"))
        text = (result_evt.get("result") or "").strip()
        if not text:
            text = "\n".join(final_text_blocks).strip()
        if is_err:
            st.mark_error(chat_id, text or "unknown error")
            return ClaudeResult(text=text or "❌ 处理失败。", state=st.ProcState.ERROR.value,
                                session_id=session_id, is_error=True, error=text, duration_ms=duration)
        st.mark_done(chat_id, text)
        return ClaudeResult(text=text or "（无内容）", state=st.ProcState.DONE.value,
                            session_id=session_id, duration_ms=duration)

    # 没有 result 事件：用累积文本兜底
    text = "\n".join(final_text_blocks).strip()
    if text:
        st.mark_done(chat_id, text)
        return ClaudeResult(text=text, state=st.ProcState.DONE.value, session_id=session_id)

    st.mark_error(chat_id, "无输出")
    return ClaudeResult(text="抱歉，没有得到回复，请重试。", state=st.ProcState.ERROR.value,
                        session_id=session_id, is_error=True, error="empty output")
