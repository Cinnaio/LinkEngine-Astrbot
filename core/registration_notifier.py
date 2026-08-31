"""EnderPass registration webhook receiver and OneBot group notifier."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections import deque
from typing import Any, Optional

from astrbot.api import logger


class RegistrationNotifier:
    """Verify EnderPass events and send registration notices to configured groups."""

    def __init__(self, secret: str = "", groups: Optional[list] = None):
        self.secret = str(secret or "").strip()
        raw_groups = [groups] if isinstance(groups, (str, int)) else (groups or [])
        self.groups = [
            str(group).strip() for group in raw_groups if str(group).strip()
        ]
        self._bot: Any = None
        self._pending: deque[dict[str, Any]] = deque(maxlen=50)
        self._seen: deque[str] = deque(maxlen=512)
        self._flush_scheduled = False

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    def remember_bot(self, bot: Any) -> None:
        """Keep the latest OneBot client so webhook requests can send group messages."""
        if bot is None:
            return
        self._bot = bot
        if self._pending and not self._flush_scheduled:
            self._flush_scheduled = True
            try:
                asyncio.get_running_loop().create_task(self._flush_pending())
            except RuntimeError:
                self._flush_scheduled = False

    async def handle(self, body: bytes, signature: str = "") -> bool:
        """Handle one signed JSON event; return whether it was accepted."""
        if not self.configured:
            return False
        expected = hmac.new(
            self.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        supplied = (signature or "").strip()
        if supplied.lower().startswith("sha256="):
            supplied = supplied[7:]
        if not hmac.compare_digest(expected, supplied.lower()):
            logger.warning("[EnderPass] 注册通知签名校验失败")
            return False

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("[EnderPass] 注册通知不是有效 JSON")
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("event") != "auth.registration.completed":
            return True

        event_id = str(payload.get("event_id") or "")
        if event_id and event_id in self._seen:
            return True
        if event_id:
            self._seen.append(event_id)

        if not self.groups:
            logger.warning("[EnderPass] 收到注册通知，但未配置 registration_notify_groups")
            return True
        if self._bot is None:
            self._pending.append(payload)
            logger.warning("[EnderPass] 暂无可用机器人连接，注册通知已暂存")
            return True

        await self._send(payload)
        return True

    async def _flush_pending(self) -> None:
        try:
            while self._pending and self._bot is not None:
                await self._send(self._pending.popleft())
        finally:
            self._flush_scheduled = False

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._bot is None:
            return
        message = self._format(payload)
        for group in self.groups:
            try:
                await self._bot.call_action(
                    "send_group_msg", group_id=int(group), message=message
                )
            except (ValueError, TypeError):
                logger.warning(f"[EnderPass] 非法通知群号: {group}")
            except Exception as error:
                logger.warning(f"[EnderPass] 向群 {group} 发送注册通知失败: {error}")

    @staticmethod
    def _format(payload: dict[str, Any]) -> str:
        user = payload.get("user") or {}
        nickname = str(user.get("nickname") or "未设置昵称")
        uid = str(user.get("uid") or "未知")
        lines = [
            "新玩家已注册皮肤站账号，注意查收！",
            "",
            f"玩家: {nickname}（UID：{uid}）",
        ]
        invitation = payload.get("invitation") or {}
        inviter = invitation.get("inviter_uid")
        if inviter:
            inviter_nickname = str(invitation.get("inviter_nickname") or "未设置昵称")
            lines.append(f"邀请人: {inviter_nickname}（UID：{inviter}）")
        return "\n".join(lines)
