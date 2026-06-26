"""
配置模块 —— 全部从环境变量 / .env 读取，配置极简。

⚠️ 重要：本项目**不含任何真实凭据或公司信息**。`.env.example` 里的
FEISHU_APP_ID / FEISHU_APP_SECRET 都是**假占位符**，使用前必须替换成你自己飞书应用的真实值。
若检测到仍是占位符，运行时会打印醒目提醒。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger("feishu_progress")

# 一眼能认出的占位符（来自 .env.example），用于提醒用户替换
_PLACEHOLDERS = {
    "",
    "cli_xxxxxxxxxxxxxxxx",                 # 假的 App ID
    "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",      # 假的 App Secret
    "your_app_id_here",
    "your_app_secret_here",
}


def _looks_like_placeholder(value: str) -> bool:
    return value.strip() in _PLACEHOLDERS


@dataclass
class Config:
    """运行所需的全部配置。"""

    # ── 飞书应用凭据（必填，去飞书开放平台拿）──
    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    # ── Claude Code CLI ──
    claude_cli_path: str = "claude"          # claude 可执行文件，默认走 PATH
    claude_model: str = ""                   # 留空 = 用 CLI 默认模型
    claude_work_dir: str = ""                # 留空 = 当前目录
    claude_add_dirs: list[str] = field(default_factory=list)  # --add-dir 授权目录

    # ── 行为参数 ──
    timeout: int = 300                       # 单次任务超时（秒），超时按 PID 结束进程树
    throttle_seconds: float = 5.0            # 进度节流间隔（秒），防刷屏
    skip_permissions: bool = True            # 是否加 --dangerously-skip-permissions

    # ── 飞书 OpenAPI 基址（一般无需改）──
    feishu_base_url: str = "https://open.feishu.cn"

    @classmethod
    def from_env(cls, *, warn: bool = True) -> "Config":
        """从环境变量构建配置。建议配合 python-dotenv 在入口处 load_dotenv()。"""
        add_dirs_raw = os.getenv("CLAUDE_ADD_DIRS", "").strip()
        add_dirs = [d.strip() for d in add_dirs_raw.split(",") if d.strip()] if add_dirs_raw else []

        cfg = cls(
            feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
            feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            claude_cli_path=os.getenv("CLAUDE_CLI_PATH", "claude"),
            claude_model=os.getenv("CLAUDE_MODEL", ""),
            claude_work_dir=os.getenv("CLAUDE_WORK_DIR", ""),
            claude_add_dirs=add_dirs,
            timeout=int(os.getenv("CLAUDE_TIMEOUT", "300")),
            throttle_seconds=float(os.getenv("PROGRESS_THROTTLE_SECONDS", "5")),
            skip_permissions=os.getenv("CLAUDE_SKIP_PERMISSIONS", "1") not in ("0", "false", "False"),
            feishu_base_url=os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn"),
        )
        if warn:
            cfg.warn_if_placeholder()
        return cfg

    def warn_if_placeholder(self) -> bool:
        """凭据仍是占位符时打印醒目提醒。返回 True 表示存在未替换的占位符。"""
        bad = _looks_like_placeholder(self.feishu_app_id) or _looks_like_placeholder(self.feishu_app_secret)
        if bad:
            logger.warning(
                "⚠️  检测到飞书凭据仍是占位符/为空！请在 .env 中把 FEISHU_APP_ID / "
                "FEISHU_APP_SECRET 替换成你自己飞书应用的真实值，否则无法发送消息。"
            )
        return bad

    def validate(self) -> None:
        """硬校验：缺凭据直接抛错（用在真正要发消息前）。"""
        if _looks_like_placeholder(self.feishu_app_id) or _looks_like_placeholder(self.feishu_app_secret):
            raise ValueError(
                "飞书凭据未配置（仍是占位符或为空）。请设置 FEISHU_APP_ID / FEISHU_APP_SECRET。"
            )
