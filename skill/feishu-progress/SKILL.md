---
name: feishu-progress
description: 安装、配置、接入与管理「飞书实时进度推送」功能（feishu-progress-push）。当用户想把 Claude Code 任务的执行进度推送到飞书、查看任务状态、配置飞书凭据、或把该功能接入自己的飞书机器人时使用。
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# /feishu-progress — 飞书实时进度推送：安装 · 配置 · 接入 · 管理

本技能用于管理 **feishu-progress-push** 组件：把长耗时的 `claude -p` 任务执行过程
节流推送到飞书，并提供执行/完成/超时/异常状态查询。

传入参数：`$ARGUMENTS`

> 安全约束：**绝不**用按进程名（`taskkill /IM claude.exe` 或 `node.exe`）的方式杀进程——
> 那会误杀用户其它 Claude 会话。超时只允许按 PID 结束本次任务进程树（组件已内置）。

---

## 按参数分派

### 无参数 / `status` —— 给出整体状态

1. 定位组件目录（默认 `feishu-progress-push/`，或询问用户路径）。
2. 检查是否存在 `.env`，凭据是否仍是占位符（`cli_xxxx...` / 全 x）。
3. 检查 `claude` CLI 是否可用（`claude --version`）。
4. 汇报：已安装？已配置？示例机器人是否在跑（查 8000 端口或用户指定端口）？
5. 给出下一步建议（配置 / 接入 / 启动）。

### `install` —— 安装

1. 若用户还没有代码：`git clone https://github.com/<user>/feishu-progress-push.git`。
2. `pip install -r requirements.txt`（库本身只需 `httpx`）。
3. 确认 `claude` CLI 已安装且为较新版本（需支持 `--output-format stream-json`）。

### `configure` —— 配置（核心，务必提醒替换占位符）

1. `cp .env.example .env`（已存在则不要覆盖，改用 Edit）。
2. **提醒用户**：`.env.example` 里的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 是**假占位符**，
   必须替换成在 https://open.feishu.cn 创建的企业自建应用的真实凭据。
3. 若用户已提供真实凭据，用 Edit 写入 `.env`（**只写 .env，永远不要写进任何会提交 git 的文件**）。
4. 视需要设置 `CLAUDE_CLI_PATH`、`PROGRESS_THROTTLE_SECONDS`（节流间隔）、`CLAUDE_TIMEOUT`。
5. 校验：运行 `python -c "from feishu_progress import Config; Config.from_env()"`，
   若打印占位符警告则提示用户继续填。

### `integrate` —— 接入到已有飞书机器人

在用户的回调处理里，调用：

```python
from feishu_progress import Config, FeishuNotifier, run_claude_with_progress, format_status

cfg = Config.from_env()
notifier = FeishuNotifier(cfg)

# 收到文本消息后：
if text in ("/status", "/状态"):
    await notifier.send_text(chat_id, format_status(chat_id))
else:
    result = await run_claude_with_progress(
        prompt=text, chat_id=chat_id, config=cfg,
        session_id=prev_sid, is_new=(prev_sid is None), notifier=notifier,
    )
    save_session(chat_id, result.session_id)
    await notifier.send_text(chat_id, result.text)   # 最终回复照常发
```

要点：进度推送由组件内部完成；`/status` 命令需机器人自己路由到 `format_status()`。

### `run` —— 启动示例机器人

```bash
cd feishu-progress-push/examples
python minimal_bot.py
```
后台常驻（Windows，脱离当前终端）：
```powershell
Start-Process python -ArgumentList "minimal_bot.py" -WindowStyle Hidden -PassThru
```
记录返回的 PID 到文件，**停止时按 PID** `Stop-Process -Id <pid>`，不要按进程名。

### `test` —— 自检

运行组件自带的解析单测（用样例事件，不真正调飞书）：
```bash
python tests/test_progress_parse.py
```

---

## 常见问题排查

| 现象 | 排查 |
|---|---|
| 飞书收不到进度 | `.env` 凭据是否真实；应用是否有发消息权限；`format_status` 与 `/status` 是否接好 |
| 进度太频繁 | 调大 `PROGRESS_THROTTLE_SECONDS` |
| 看不到工具步骤 | claude CLI 版本是否支持 `--output-format stream-json --verbose` |
| 超时后疑似杀错进程 | 确认未在外部用 `taskkill /IM` 群杀；组件只按 PID 杀树 |
