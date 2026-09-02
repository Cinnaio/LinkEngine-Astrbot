"""EnderPass registration webhook receiver and OneBot group notifier."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections import deque
from pathlib import Path
from typing import Any, Optional

from astrbot.api import logger


class RegistrationNotifier:
    """Verify EnderPass events and send registration notices to configured groups."""

    def __init__(
        self,
        secret: str = "",
        groups: Optional[list] = None,
        state_path: Optional[Path] = None,
    ):
        self.secret = str(secret or "").strip()
        raw_groups = [groups] if isinstance(groups, (str, int)) else (groups or [])
        self.groups = [
            str(group).strip() for group in raw_groups if str(group).strip()
        ]
        self._bot: Any = None
        self._pending: deque[dict[str, Any]] = deque(maxlen=50)
        self._seen: deque[str] = deque(maxlen=512)
        self._flush_scheduled = False
        self._flush_lock = asyncio.Lock()
        self._state_path = Path(state_path) if state_path else None
        self._load_state()

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

        if not self.groups:
            if event_id:
                self._seen.append(event_id)
                self._persist_state()
            logger.warning("[EnderPass] 收到注册通知，但未配置 registration_notify_groups")
            return True

        if event_id:
            self._seen.append(event_id)
        if self._bot is None:
            self._pending.append(payload)
            self._persist_state()
            logger.warning("[EnderPass] 暂无可用机器人连接，注册通知已暂存")
            return True

        self._pending.append(payload)
        self._persist_state()
        await self._flush_pending()
        return True

    async def _flush_pending(self) -> None:
        async with self._flush_lock:
            try:
                while self._pending and self._bot is not None:
                    payload = self._pending[0]
                    if not await self._send(payload):
                        break
                    self._pending.popleft()
                    self._persist_state()
            finally:
                self._flush_scheduled = False

    async def _send(self, payload: dict[str, Any]) -> bool:
        if self._bot is None:
            return False
        message = self._format(payload)
        delivered = True
        for group in self.groups:
            try:
                await self._bot.call_action(
                    "send_group_msg", group_id=int(group), message=message
                )
            except (ValueError, TypeError):
                logger.warning(f"[EnderPass] 非法通知群号: {group}")
                delivered = False
            except Exception as error:
                logger.warning(f"[EnderPass] 向群 {group} 发送注册通知失败: {error}")
                delivered = False
        return delivered

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.is_file():
            return
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                return
            seen = state.get("seen", [])
            pending = state.get("pending", [])
            if isinstance(seen, list):
                self._seen.extend(str(item) for item in seen[-512:] if item)
            if isinstance(pending, list):
                self._pending.extend(
                    item for item in pending[-50:] if isinstance(item, dict)
                )
        except Exception as error:
            logger.warning(f"[EnderPass] 读取注册通知状态失败: {error}")

    def _persist_state(self) -> None:
        if self._state_path is None:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "seen": list(self._seen),
                        "pending": list(self._pending),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            temporary.replace(self._state_path)
        except Exception as error:
            logger.warning(f"[EnderPass] 保存注册通知状态失败: {error}")

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
        registered_at = user.get("registered_at")
        if registered_at:
            lines.append(f"注册时间: {str(registered_at).replace('T', ' ').split('.', 1)[0].rstrip('Z')}")
        invitation = payload.get("invitation") or {}
        inviter = invitation.get("inviter_uid")
        if inviter:
            inviter_nickname = str(invitation.get("inviter_nickname") or "未设置昵称")
            lines.append(f"邀请人: {inviter_nickname}（UID：{inviter}）")
            preview = str(invitation.get("code_preview") or "")
            if preview:
                lines.append(f"使用邀请码: ••••{preview}")
        return "\n".join(lines)
