"""
飞书消息发送封装 —— 只依赖 httpx，直接调用飞书 OpenAPI（无需飞书 SDK）。

负责：获取 tenant_access_token（带缓存）、发送文本消息。
"""
from __future__ import annotations

import logging
import time

import httpx

from .config import Config

logger = logging.getLogger("feishu_progress")


class FeishuNotifier:
    """向飞书会话发送消息。线程/协程安全性：token 缓存为简单字段，单进程使用足够。"""

    def __init__(self, config: Config):
        self.config = config
        self._token: str = ""
        self._token_expire_at: float = 0.0

    async def _get_token(self) -> str:
        """获取 tenant_access_token，提前 60s 过期重取。"""
        now = time.time()
        if self._token and now < self._token_expire_at - 60:
            return self._token

        url = f"{self.config.feishu_base_url}/open-apis/auth/v3/tenant_access_token/internal"
        body = {
            "app_id": self.config.feishu_app_id,
            "app_secret": self.config.feishu_app_secret,
        }
        # trust_env=False：不走系统代理，避免内网/代理环境下连不上飞书
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            resp = await client.post(url, json=body)
            data = resp.json() if resp.status_code == 200 else {}
            if resp.status_code == 200 and data.get("code") == 0:
                self._token = data["tenant_access_token"]
                self._token_expire_at = now + data.get("expire", 7200)
                return self._token
            raise RuntimeError(
                f"获取 tenant_access_token 失败: status={resp.status_code} body={resp.text[:300]}"
            )

    async def send_text(self, chat_id: str, text: str) -> bool:
        """发送文本消息到指定会话。返回是否成功。"""
        import json

        try:
            token = await self._get_token()
        except Exception as e:
            logger.error(f"发送失败（取 token）：{e}")
            return False

        url = f"{self.config.feishu_base_url}/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        params = {"receive_id_type": "chat_id"}
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, params=params, json=payload)
            data = resp.json() if resp.status_code == 200 else {}
            if resp.status_code == 200 and data.get("code") == 0:
                return True
            logger.error(f"发送消息失败: status={resp.status_code} body={resp.text[:300]}")
            return False
        except Exception as e:
            logger.exception(f"发送消息异常: {e}")
            return False
