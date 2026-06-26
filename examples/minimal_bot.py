"""
最小可运行示例：一个把 Claude Code 接入飞书、并带「实时进度推送 + 状态查询」的机器人。

运行：
    pip install -r ../requirements.txt
    cp ../.env.example .env   # 然后填入真实的飞书凭据
    python minimal_bot.py

把本机用 ngrok 之类暴露出去，在飞书开放平台「事件订阅」里把回调地址配成
    https://<你的域名>/feishu/event

在飞书里 @机器人 发消息即可；发送 /status 查看当前任务状态。
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
import uvicorn

# 让示例能直接 import 上一级的 feishu_progress 包（无需先 pip install）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feishu_progress import (  # noqa: E402
    Config,
    FeishuNotifier,
    run_claude_with_progress,
    format_status,
)

load_dotenv()

config = Config.from_env()          # 会在凭据是占位符时打印提醒
notifier = FeishuNotifier(config)

# 简单的会话记忆：chat_id -> session_id（让多轮对话保持上下文）
_sessions: dict[str, str] = {}

app = FastAPI(title="feishu-progress-push 示例")


@app.get("/feishu/event")
async def verify_get():
    return Response(content="ok", status_code=200)


@app.post("/feishu/event")
async def feishu_event(request: Request):
    body = await request.body()
    data = json.loads(body or "{}")

    # 飞书回调地址验证
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge", "")}

    event = data.get("event", {}) or {}
    message = event.get("message", {}) or {}
    if message.get("message_type") == "text":
        chat_id = message.get("chat_id", "")
        text = json.loads(message.get("content", "{}")).get("text", "").strip()
        # 去掉 @ 机器人 的标记
        text = text.replace("@_user_1", "").strip()
        if chat_id and text:
            # 飞书要求快速回 200，处理放到后台任务
            asyncio.create_task(handle(chat_id, text))

    return Response(content="{}", status_code=200, media_type="application/json")


async def handle(chat_id: str, text: str):
    # /status 命令：直接回当前状态
    if text in ("/status", "/状态", "/进程"):
        await notifier.send_text(chat_id, format_status(chat_id))
        return

    # 先回执一条，让用户立刻知道已收到
    await notifier.send_text(chat_id, "🤖 收到，正在处理中…（随时发 /status 查看进度）")

    sid = _sessions.get(chat_id)
    result = await run_claude_with_progress(
        prompt=text,
        chat_id=chat_id,
        config=config,
        session_id=sid,
        is_new=(sid is None),
        notifier=notifier,
    )
    _sessions[chat_id] = result.session_id      # 记住 session，下次续接

    # 最终回复始终照常发送
    await notifier.send_text(chat_id, result.text)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
