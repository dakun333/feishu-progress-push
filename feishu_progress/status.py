"""
进程状态注册表 —— 跟踪每个飞书会话当前 Claude 任务的状态，
供 `/status` 这类命令实时查询：执行中 / 已完成 / 超时 / 异常 / 空闲。
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional


class ProcState(str, Enum):
    IDLE = "idle"          # 空闲，无任务
    RUNNING = "running"    # 执行中
    DONE = "done"          # 正常完成
    TIMEOUT = "timeout"    # 超时被终止
    ERROR = "error"        # 异常


# chat_id -> 状态字典
_status: dict[str, dict] = {}


def _now() -> float:
    return time.time()


def mark_running(chat_id: str, *, pid: Optional[int], session_id: str, task: str) -> None:
    _status[chat_id] = {
        "state": ProcState.RUNNING,
        "pid": pid,
        "session_id": session_id,
        "task": task[:200],
        "started_at": _now(),
        "finished_at": None,
        "last_progress": "",
        "error": None,
        "reply_preview": None,
    }


def update_pid(chat_id: str, pid: int) -> None:
    if chat_id in _status:
        _status[chat_id]["pid"] = pid


def update_progress(chat_id: str, progress_line: str) -> None:
    if chat_id in _status:
        _status[chat_id]["last_progress"] = progress_line


def mark_done(chat_id: str, reply_preview: str = "") -> None:
    s = _status.get(chat_id)
    if s:
        s["state"] = ProcState.DONE
        s["finished_at"] = _now()
        s["reply_preview"] = reply_preview[:200]


def mark_timeout(chat_id: str) -> None:
    s = _status.get(chat_id)
    if s:
        s["state"] = ProcState.TIMEOUT
        s["finished_at"] = _now()


def mark_error(chat_id: str, error: str) -> None:
    s = _status.get(chat_id)
    if s:
        s["state"] = ProcState.ERROR
        s["finished_at"] = _now()
        s["error"] = (error or "")[:300]


def get_status(chat_id: str) -> Optional[dict]:
    """返回原始状态字典（含实时计算的 elapsed），无记录返回 None。"""
    s = _status.get(chat_id)
    if not s:
        return None
    out = dict(s)
    end = s["finished_at"] or _now()
    out["elapsed"] = round(end - s["started_at"], 1)
    return out


def all_status() -> dict[str, dict]:
    """返回所有会话的状态快照。"""
    return {cid: get_status(cid) for cid in _status}


def format_status(chat_id: str) -> str:
    """把状态格式化为适合直接发回飞书的中文文本。"""
    s = get_status(chat_id)
    if not s:
        return "💤 当前空闲，没有正在执行或最近执行的任务。"

    state: ProcState = s["state"]
    elapsed = s["elapsed"]
    sid = (s.get("session_id") or "")[:8]
    pid = s.get("pid")
    task = s.get("task") or ""
    last = s.get("last_progress") or ""

    if state == ProcState.RUNNING:
        lines = [
            f"🔄 执行中 | 已运行 {elapsed}s",
            f"PID {pid} | session={sid}",
        ]
        if task:
            lines.append(f"当前任务：{task}")
        if last:
            lines.append(f"最近动作：{last}")
        return "\n".join(lines)

    if state == ProcState.DONE:
        preview = s.get("reply_preview") or ""
        text = f"✅ 上一次已完成 | 耗时 {elapsed}s"
        if preview:
            text += f"\n回复预览：{preview}"
        return text

    if state == ProcState.TIMEOUT:
        return f"⏰ 上一次超时被终止 | 耗时 {elapsed}s（已按 PID 结束该任务进程树）"

    if state == ProcState.ERROR:
        return f"❌ 上一次异常 | 耗时 {elapsed}s\n原因：{s.get('error')}"

    return "💤 当前空闲。"
