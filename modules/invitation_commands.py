"""AstrBot commands for EnderPass invitations."""

from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent

from ..core.binding_store import BindingStore
from ..core.enderpass_client import EnderPassClient


class InvitationModule:
    """Keep invitation presentation in AstrBot while EnderPass owns the data."""

    name = "invitation"

    def __init__(
        self,
        client: EnderPassClient,
        store: BindingStore,
        history_limit: int = 10,
        invitee_limit: int = 20,
    ):
        self.client = client
        self.store = store
        self.history_limit = max(1, min(20, int(history_limit or 10)))
        self.invitee_limit = max(1, min(50, int(invitee_limit or 20)))

    async def cmd_summary(self, event: AstrMessageEvent) -> str:
        private_error = self._private_only(event)
        if private_error:
            return private_error

        binding, error = await self._binding_for(event)
        if error:
            return error

        response = await self.client.get_summary(binding.sub)
        if not response.get("success"):
            return self._error_message(response, "获取邀请概览失败")

        data = response.get("data") or {}
        if not isinstance(data, dict):
            return "EnderPass 返回的邀请概览格式无效"

        playtime = data.get("playtimeMs")
        minimum = data.get("minimumPlaytimeMs")
        lines = [
            "邀请概览:",
            f"  皮肤站 UID: {data.get('uid', binding.sub)}",
            f"  Minecraft 角色: {data.get('playerName') or binding.player_name or '-'}",
            f"  累计活跃: {self._duration(playtime)}",
            f"  生成门槛: {self._duration(minimum)}",
        ]

        status = str(data.get("eligibilityStatus") or "")
        if status == "eligible":
            lines.append("  生成资格: 已达标")
        elif status == "not-eligible":
            lines.append(
                f"  生成资格: 未达标，还需 {self._duration(data.get('remainingPlaytimeMs'))}"
            )
        elif status == "no-player":
            lines.append("  生成资格: 请先在皮肤站绑定 Minecraft 角色")
        elif status == "stats-unavailable":
            lines.append("  生成资格: 暂时无法读取服务器活跃时长")
        else:
            lines.append("  生成资格: 暂不可用")

        lines.extend([
            f"  注册模式: {self._registration_mode(data.get('registrationMode'))}",
            f"  已邀请玩家: {data.get('invitedCount', 0)} 人",
            f"  邀请码记录: {data.get('invitationCount', 0)} 条（有效 {data.get('activeInvitationCount', 0)} 条）",
        ])
        return "\n".join(lines)

    async def cmd_generate(self, event: AstrMessageEvent) -> str:
        private_error = self._private_only(event)
        if private_error:
            return private_error

        binding, error = await self._binding_for(event)
        if error:
            return error

        response = await self.client.generate_invitation(binding.sub)
        if not response.get("success"):
            return self._error_message(response, "生成邀请码失败")

        data = response.get("data") or {}
        if not isinstance(data, dict) or not data.get("code"):
            return "EnderPass 未返回完整邀请码，请稍后在邀请记录中查看"

        expires = self._date(data.get("expiresAt")) if data.get("expiresAt") else "永不过期"
        return "\n".join([
            "邀请码已生成:",
            f"  邀请码: {data['code']}",
            f"  注册链接: {data.get('registrationUrl', '-')}",
            f"  有效期: {expires}",
            f"  使用次数: {data.get('usedCount', 0)}/{data.get('maxUses', 1)}",
            "请不要在群聊中转发完整邀请码。",
        ])

    async def cmd_history(self, event: AstrMessageEvent) -> str:
        private_error = self._private_only(event)
        if private_error:
            return private_error

        binding, error = await self._binding_for(event)
        if error:
            return error

        response = await self.client.get_history(binding.sub)
        if not response.get("success"):
            return self._error_message(response, "获取邀请记录失败")

        data = response.get("data") or {}
        entries = data.get("entries", []) if isinstance(data, dict) else []
        if not entries:
            return "你还没有生成过邀请码"

        lines = [f"邀请码记录（最近 {min(len(entries), self.history_limit)} 条）:"]
        for entry in entries[: self.history_limit]:
            code = entry.get("code") or entry.get("preview") or "-"
            status = self._status(entry.get("status"))
            expires = self._date(entry.get("expiresAt")) if entry.get("expiresAt") else "永不过期"
            lines.append(
                f"  #{entry.get('id', '?')} {code} | {status} | "
                f"{entry.get('usedCount', 0)}/{entry.get('maxUses', 1)} | 到期 {expires}"
            )
        if len(entries) > self.history_limit:
            lines.append(f"  ……还有 {len(entries) - self.history_limit} 条，请查看皮肤站玩家中心")
        return "\n".join(lines)

    async def cmd_invitees(self, event: AstrMessageEvent) -> str:
        private_error = self._private_only(event)
        if private_error:
            return private_error

        binding, error = await self._binding_for(event)
        if error:
            return error

        response = await self.client.get_invitees(binding.sub)
        if not response.get("success"):
            return self._error_message(response, "获取邀请名单失败")

        data = response.get("data") or {}
        entries = data.get("entries", []) if isinstance(data, dict) else []
        if not entries:
            return "还没有玩家使用你的邀请码完成注册"

        lines = [f"邀请名单（共 {len(entries)} 人）:"]
        for entry in entries[: self.invitee_limit]:
            name = entry.get("name") or entry.get("nickname") or f"UID #{entry.get('uid', '?')}"
            code = entry.get("code") or "-"
            lines.append(
                f"  {name}（UID {entry.get('uid', '?')}）| "
                f"邀请码 {code} | {self._date(entry.get('usedAt'))}"
            )
        if len(entries) > self.invitee_limit:
            lines.append(f"  ……还有 {len(entries) - self.invitee_limit} 人，请查看皮肤站玩家中心")
        return "\n".join(lines)

    async def cmd_leaderboard(self, event: AstrMessageEvent, raw_limit: str = "") -> str:
        limit = 10
        if raw_limit and raw_limit.strip():
            try:
                limit = max(1, min(20, int(raw_limit.strip())))
            except ValueError:
                return "用法: /邀请榜 [数量]（数量为 1-20 的整数）"

        binding = await self.store.get_by_qq(str(event.get_sender_id()))
        uid = binding.sub if binding else None
        response = await self.client.get_leaderboard(limit, uid)
        if not response.get("success"):
            return self._error_message(response, "获取邀请排行榜失败")

        data = response.get("data") or {}
        entries = data.get("entries", []) if isinstance(data, dict) else []
        if not entries:
            return "暂无邀请排行数据"

        lines = [f"全服邀请排行榜（前 {len(entries)}）:"]
        for entry in entries:
            current = "（你）" if entry.get("isCurrent") else ""
            name = entry.get("name") or entry.get("nickname") or f"UID #{entry.get('uid', '?')}"
            lines.append(
                f"  #{entry.get('rank', '?')} {name}{current} - "
                f"{entry.get('invitedCount', 0)} 人"
            )
        return "\n".join(lines)

    async def cmd_revoke(self, event: AstrMessageEvent, raw_id: str = "") -> str:
        private_error = self._private_only(event)
        if private_error:
            return private_error
        if not raw_id or not raw_id.strip().isdigit():
            return "用法: /撤销邀请码 <记录编号>（编号可通过 /邀请记录 查看）"

        binding, error = await self._binding_for(event)
        if error:
            return error

        response = await self.client.revoke_invitation(binding.sub, int(raw_id.strip()))
        if not response.get("success"):
            return self._error_message(response, "撤销邀请码失败")
        return f"邀请码记录 #{int(raw_id.strip())} 已撤销"

    async def _binding_for(self, event: AstrMessageEvent):
        if not self.client.configured:
            return None, "管理员尚未配置 EnderPass 邀请 API，相关功能暂不可用"

        binding = await self.store.get_by_qq(str(event.get_sender_id()))
        if not binding:
            return None, "你还没有绑定皮肤站账号，发送 /绑定 后再试"
        if not binding.sub:
            return None, "你的绑定记录缺少皮肤站 UID，请重新发送 /绑定"
        return binding, None

    @staticmethod
    def _private_only(event: AstrMessageEvent) -> str:
        try:
            if event.get_group_id():
                return "邀请码包含敏感信息，请私聊机器人使用此命令"
        except Exception:
            pass
        return ""

    @staticmethod
    def _error_message(response: dict[str, Any], fallback: str) -> str:
        message = response.get("message")
        return str(message) if message else fallback

    @staticmethod
    def _status(status: Any) -> str:
        return {
            "active": "有效",
            "exhausted": "已用尽",
            "expired": "已过期",
            "revoked": "已撤销",
        }.get(str(status or ""), "未知")

    @staticmethod
    def _registration_mode(mode: Any) -> str:
        return {
            "invite-cracked": "普通注册需要邀请码",
            "open": "普通注册开放",
            "closed": "普通注册关闭",
        }.get(str(mode or ""), "未知")

    @staticmethod
    def _date(value: Any) -> str:
        return str(value or "-").replace("T", " ").split(".", 1)[0].rstrip("Z")

    @staticmethod
    def _duration(milliseconds: Any) -> str:
        if milliseconds is None:
            return "未知"
        try:
            total_minutes = max(0, int(milliseconds)) // 60000
        except (TypeError, ValueError):
            return "未知"
        days, remainder = divmod(total_minutes, 1440)
        hours, minutes = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小时")
        if minutes or not parts:
            parts.append(f"{minutes}分钟")
        return "".join(parts)
