# feishu-progress-push

Stream the live execution of long-running **Claude Code (`claude -p`)** tasks into **Feishu (Lark)** chat — throttled, so users see "🧠 thinking / 📖 reading file / 💻 running command…" plus the task's **running / done / timeout / error** status.

> Plug-and-play · No company/private info · Minimal config · Only depends on `httpx`

**🌐 Language / 语言** — click a section below to expand:

<details open>
<summary><b>📖 English</b></summary>

<br>

## Why

When you wire `claude -p` to a chatbot, a complex task can take tens of seconds to minutes. During that time the chat is **silent** — users can't tell if it's stuck, still working, or crashed. This component solves three things:

1. **Live progress** — translates Claude's key actions into plain language, throttled before pushing to Feishu (no flooding).
2. **Queryable status** — send `/status` anytime to see "running (12s elapsed) / done / timeout / error".
3. **Safe timeout** — on timeout it kills **only this task's process tree by PID**, **never** by image name (so it won't kill your other Claude sessions).

## Install

```bash
git clone https://github.com/dakun333/feishu-progress-push.git
cd feishu-progress-push
pip install -r requirements.txt
```

> The library itself only needs `httpx`; `fastapi/uvicorn/python-dotenv` are for the example only.

## Configure (minimal, 3 steps)

```bash
cp .env.example .env
```

Edit `.env` and **replace the placeholders with your real values**:

```ini
FEISHU_APP_ID=cli_your_real_app_id
FEISHU_APP_SECRET=your_real_app_secret
CLAUDE_CLI_PATH=claude          # or the full path to claude.exe
```

> ⚠️ **Important**: The `FEISHU_APP_ID` / `FEISHU_APP_SECRET` in `.env.example` are **fake placeholders**.
> You must replace them with the real credentials of a custom app you create on the
> [Feishu Open Platform](https://open.feishu.cn) — otherwise messages can't be sent.
> If placeholders are still detected at runtime, a loud warning is printed. `.env` is gitignored.

| Variable | Description | Default |
|---|---|---|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | Feishu app credentials (required) | — |
| `CLAUDE_CLI_PATH` | claude executable | `claude` |
| `CLAUDE_MODEL` | model id, empty = CLI default | empty |
| `CLAUDE_WORK_DIR` | Claude working directory | cwd |
| `CLAUDE_ADD_DIRS` | `--add-dir` allowed dirs (comma-separated) | empty |
| `CLAUDE_TIMEOUT` | per-task timeout (s); on timeout kills the process tree by PID | `300` |
| `PROGRESS_THROTTLE_SECONDS` | progress throttle interval (s); larger = less chatty | `5` |
| `CLAUDE_SKIP_PERMISSIONS` | add `--dangerously-skip-permissions` | `1` |

## Quick use

```python
import asyncio
from feishu_progress import Config, run_claude_with_progress, format_status

cfg = Config.from_env()

async def main():
    result = await run_claude_with_progress(
        prompt="Analyze this code and point out potential bugs",
        chat_id="oc_xxxxxxxx",     # Feishu chat id
        config=cfg,
    )
    print(result.text)             # final reply (always returned in full, never throttled)
    print(result.session_id)       # pass back as session_id next time to continue the conversation
    print(format_status("oc_xxxxxxxx"))   # -> "✅ Last run done | 12.3s ..."

asyncio.run(main())
```

Multi-turn: pass the previous `result.session_id` as the next call's `session_id` with `is_new=False`.

A full Feishu bot example is in [`examples/minimal_bot.py`](examples/minimal_bot.py), with the `/status` command and callback handling.

## What progress looks like (after throttling)

```
🤖 Received, working on it… (send /status anytime to check progress)
🚀 Started…
🧠 Thinking…
📖 Reading file
💻 Running command
✏️ Editing file
✅ [full final reply]
```

Throttling rule: a **category change** pushes immediately (with a min-interval guard); within the same category at most one push per `PROGRESS_THROTTLE_SECONDS`; consecutive duplicates are dropped. **The final reply is always sent in full.**

`/status` example:

```
🔄 Running | 18s elapsed
PID 39284 | session=ab12cd34
Task: Analyze this code and point out potential bugs
Last action: 💻 Running command
```

## Companion Claude Code Skill

`skill/feishu-progress/SKILL.md` is a Claude Code skill to **install, configure, integrate and manage** this feature with one command. Drop it into `~/.claude/skills/feishu-progress/` and invoke `/feishu-progress` in Claude Code. See [skill/feishu-progress/SKILL.md](skill/feishu-progress/SKILL.md).

## How it works

```
user message → run_claude_with_progress()
              │  spawn: claude -p --output-format stream-json --verbose
              │          (--session-id new / --resume continue)
              ▼
        read NDJSON event stream line by line
        ├─ system/init        → 🚀 start
        ├─ assistant.tool_use → 📖/💻/✏️/🔍 ... (mapped by tool name)
        ├─ assistant.text     → 🧠 thinking
        └─ result             → final reply text
              │  each event → ThrottledProgress → FeishuNotifier push
              ▼
        return ClaudeResult(text, state, session_id)
        timeout → PID only: taskkill /PID <pid> /T /F (never by image name)
```

## Notes

- **No company/private info is uploaded**: no real credentials, no internal hostnames; all secrets live in `.env` (gitignored).
- Progress visibility relies on `claude -p --output-format stream-json --verbose` — requires a recent Claude Code CLI.
- On POSIX, to kill the whole tree on timeout, start the process in a new process group; on Windows `taskkill /T` already covers children.

</details>

<details>
<summary><b>📖 简体中文</b></summary>

<br>

## 为什么需要它

直接用 `claude -p` 接机器人时，一条复杂任务可能要跑几十秒甚至几分钟，期间飞书里**毫无反馈**，用户不知道是卡住了、还在跑、还是挂了。本组件解决三件事：

1. **实时进度**：把 Claude 执行中的关键动作翻译成人话，节流后推到飞书，不刷屏。
2. **状态可查**：随时发 `/status` 就能看到「执行中（已跑 12s）/ 已完成 / 超时 / 异常」。
3. **安全超时**：超时只按 **PID** 结束**本次任务**的进程树，**绝不**按进程名群杀（不会误杀你其它的 Claude 会话）。

## 安装

```bash
git clone https://github.com/dakun333/feishu-progress-push.git
cd feishu-progress-push
pip install -r requirements.txt
```

> 库本身只需要 `httpx`；`fastapi/uvicorn/python-dotenv` 仅示例用。

## 配置（极简，3 步）

```bash
cp .env.example .env
```

编辑 `.env`，**把占位符换成你自己的真实值**：

```ini
FEISHU_APP_ID=cli_你的真实AppID
FEISHU_APP_SECRET=你的真实AppSecret
CLAUDE_CLI_PATH=claude          # 或 claude.exe 的完整路径
```

> ⚠️ **重要提醒**：`.env.example` 里的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 都是**假占位符**，
> 必须替换成你在 [飞书开放平台](https://open.feishu.cn) 创建的企业自建应用的真实凭据，否则无法发消息。
> 若运行时检测到仍是占位符，会打印醒目警告。`.env` 已被 `.gitignore`，不会误提交。

| 变量 | 说明 | 默认 |
|---|---|---|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书应用凭据（必填） | — |
| `CLAUDE_CLI_PATH` | claude 可执行文件 | `claude` |
| `CLAUDE_MODEL` | 指定模型，留空用默认 | 空 |
| `CLAUDE_WORK_DIR` | Claude 工作目录 | 当前目录 |
| `CLAUDE_ADD_DIRS` | `--add-dir` 授权目录（逗号分隔） | 空 |
| `CLAUDE_TIMEOUT` | 单次超时（秒），超时按 PID 结束进程树 | `300` |
| `PROGRESS_THROTTLE_SECONDS` | 进度节流间隔（秒），越大越不刷屏 | `5` |
| `CLAUDE_SKIP_PERMISSIONS` | 是否加 `--dangerously-skip-permissions` | `1` |

## 快速使用

```python
import asyncio
from feishu_progress import Config, run_claude_with_progress, format_status

cfg = Config.from_env()

async def main():
    result = await run_claude_with_progress(
        prompt="帮我分析这段代码并指出潜在 bug",
        chat_id="oc_xxxxxxxx",     # 飞书会话 id
        config=cfg,
    )
    print(result.text)             # 最终回复（始终完整返回，不受进度节流影响）
    print(result.session_id)       # 本次 session，下次传入即可续接上下文
    print(format_status("oc_xxxxxxxx"))   # → "✅ 上一次已完成 | 耗时 12.3s ..."

asyncio.run(main())
```

多轮对话：把上次返回的 `result.session_id` 作为下次的 `session_id` 传入，并设 `is_new=False`。

完整的飞书机器人示例见 [`examples/minimal_bot.py`](examples/minimal_bot.py)，含 `/status` 命令与回调处理。

## 进度长什么样（节流后）

```
🤖 收到，正在处理中…（随时发 /status 查看进度）
🚀 已开始处理…
🧠 正在思考…
📖 正在读取文件
💻 正在执行命令
✏️ 正在修改文件
✅ [最终回复全文]
```

节流规则：进度**类别变化**时立即推（有最小间隔保护），同一类别持续时每 `PROGRESS_THROTTLE_SECONDS` 秒最多推一条，连续重复不重发。**最终回复永远完整发送。**

`/status` 返回示例：

```
🔄 执行中 | 已运行 18s
PID 39284 | session=ab12cd34
当前任务：帮我分析这段代码并指出潜在 bug
最近动作：💻 正在执行命令
```

## 配套 Claude Code Skill

仓库 `skill/feishu-progress/SKILL.md` 是一个 Claude Code 技能，用来**一键安装、配置、接入、管理**本功能。
把它放到 `~/.claude/skills/feishu-progress/` 即可在 Claude Code 里用 `/feishu-progress` 调用。详见 [skill/feishu-progress/SKILL.md](skill/feishu-progress/SKILL.md)。

## 工作原理

```
用户消息 → run_claude_with_progress()
              │  spawn: claude -p --output-format stream-json --verbose
              │          (--session-id 新建 / --resume 续接)
              ▼
        逐行读取 NDJSON 事件流
        ├─ system/init        → 🚀 开始
        ├─ assistant.tool_use → 📖/💻/✏️/🔍 ... （按工具名映射）
        ├─ assistant.text     → 🧠 正在思考
        └─ result             → 最终回复文本
              │  每个事件喂给 ThrottledProgress（节流）→ FeishuNotifier 推送
              ▼
        返回 ClaudeResult(text, state, session_id)
        超时 → 仅按 PID: taskkill /PID <pid> /T /F（绝不按进程名）
```

## 注意事项

- **不会上传任何公司/私密信息**：本仓库不含真实凭据、不含任何内网地址；所有敏感项都在 `.env`（被忽略）。
- 进度可见性依赖 `claude -p --output-format stream-json --verbose` 的事件流，需较新版本的 Claude Code CLI。
- POSIX 上若要超时杀整棵进程树，建议自行以新进程组启动；Windows 用 `taskkill /T` 已覆盖子进程。

</details>

## License

MIT
