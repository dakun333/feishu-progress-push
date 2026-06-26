# feishu-progress-push

Stream the live execution of long-running **Claude Code (`claude -p`)** tasks into **Feishu (Lark)** chat — throttled, so users see "🧠 thinking / 📖 reading file / 💻 running command…" plus the task's **running / done / timeout / error** status.

> Plug-and-play · Minimal config · Only depends on `httpx`

[📖 中文文档](README_zh.md)

---

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

- Progress visibility relies on `claude -p --output-format stream-json --verbose` — requires a recent Claude Code CLI.
- On POSIX, to kill the whole tree on timeout, start the process in a new process group; on Windows `taskkill /T` already covers children.

## License

MIT
