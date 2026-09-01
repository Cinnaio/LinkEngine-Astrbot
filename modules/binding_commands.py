"""QQ <-> skin station account binding commands and group-join welcome."""

from typing import TYPE_CHECKING, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At

from ..core.binding_store import Binding, BindingStore, format_uuid
from ..core.oidc_client import OidcClient, OidcError

if TYPE_CHECKING:
    from astrbot.api.star import Context

    from ..core.permission import PermissionChecker


def _mask_qq(qq: str) -> str:
    if len(qq) <= 5:
        return qq
    return f"{qq[:2]}****{qq[-3:]}"


def _target_from_event(event: AstrMessageEvent, fallback: str = "") -> str:
    """优先取消息中 @ 的用户 QQ,没有 @ 时回退到文本参数。"""
    try:
        self_id = str(event.get_self_id())
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                qq = str(comp.qq)
                if qq and qq not in ("all", self_id):
                    return qq
    except Exception:
        pass
    return (fallback or "").strip()


class BindingModule:
    """皮肤站账号绑定:发起 OIDC 授权、处理回调、入群欢迎。"""

    name = "binding"

    def __init__(
        self,
        store: BindingStore,
        oidc: OidcClient,
        permission: "PermissionChecker",
        context: "Context",
        watch_groups: Optional[list] = None,
        auto_set_group_card: bool = True,
    ):
        self.store = store
        self.oidc = oidc
        self.permission = permission
        self.context = context
        self.watch_groups = [str(g) for g in (watch_groups or [])]
        self.auto_set_group_card = auto_set_group_card

    # ==================== 命令 ====================

    async def cmd_bind(self, event: AstrMessageEvent) -> str:
        """/绑定 - 生成本人专属的皮肤站授权链接"""
        if not self.oidc.configured:
            return "管理员尚未配置皮肤站 OIDC 参数,暂时无法绑定"

        qq = str(event.get_sender_id())
        lines = []
        existing = await self.store.get_by_qq(qq)
        if existing:
            shown = existing.player_name or existing.nickname or existing.sub
            lines.append(f"你当前已绑定「{shown}」,重新授权将覆盖旧绑定。")
        else:
            lines.append("请用浏览器打开下面的链接,登录皮肤站并授权:")

        state = self.oidc.create_state(
            qq=qq,
            group_id=event.get_group_id() or "",
            origin=event.unified_msg_origin,
            bot=getattr(event, "bot", None),
        )
        lines.append(self.oidc.build_authorize_url(state))
        lines.append("链接 10 分钟内有效,仅限本人点击,完成后我会在这里通知你。")
        return "\n".join(lines)

    async def cmd_unbind(self, event: AstrMessageEvent) -> str:
        """/解绑 - 解除自己的绑定"""
        qq = str(event.get_sender_id())
        removed = await self.store.delete_by_qq(qq)
        if not removed:
            return "你还没有绑定皮肤站账号"
        shown = removed.player_name or removed.nickname or removed.sub
        return f"已解除与「{shown}」的绑定"

    async def cmd_bind_info(self, event: AstrMessageEvent) -> str:
        """/我的绑定 - 查看自己的绑定信息"""
        qq = str(event.get_sender_id())
        binding = await self.store.get_by_qq(qq)
        if not binding:
            return "你还没有绑定皮肤站账号,发送 /绑定 开始"
        return self._format_binding(binding)

    async def cmd_admin_query(
        self, event: AstrMessageEvent, target: str,
    ) -> str:
        """/查绑定 <QQ号|玩家名|@用户> - 查询绑定(管理员)"""
        target = _target_from_event(event, target)
        if not target:
            total = await self.store.count()
            return (
                f"用法: /查绑定 <QQ号|玩家名|@用户>"
                f"(当前共 {total} 条绑定)"
            )
        binding = None
        if target.isdigit():
            binding = await self.store.get_by_qq(target)
        if binding is None:
            binding = await self.store.get_by_player(target)
        if binding is None:
            return f"未找到 {target} 的绑定记录"
        return self._format_binding(binding, show_qq=True)

    async def cmd_admin_unbind(
        self, event: AstrMessageEvent, qq: str,
    ) -> str:
        """/强制解绑 <QQ号|@用户> - 解除任意绑定(管理员)"""
        qq = _target_from_event(event, qq)
        if not qq:
            return "用法: /强制解绑 <QQ号|@用户>"
        removed = await self.store.delete_by_qq(qq)
        if not removed:
            return f"QQ {qq} 没有绑定记录"
        shown = removed.player_name or removed.nickname or removed.sub
        return f"已强制解除 QQ {qq} 与「{shown}」的绑定"

    def _format_binding(self, b: Binding, show_qq: bool = False) -> str:
        lines = ["绑定信息:"]
        if show_qq:
            lines.append(f"  QQ: {b.qq}")
        lines.append(f"  皮肤站账号: {b.nickname or '-'} (uid {b.sub})")
        lines.append(f"  角色名: {b.player_name or '-'}")
        lines.append(f"  游戏 UUID: {format_uuid(b.minecraft_uuid) or '-'}")
        lines.append(f"  绑定时间: {b.bound_at}")
        return "\n".join(lines)

    # ==================== OAuth 回调 ====================

    async def handle_callback(
        self, state: str, code: str, error: str,
    ) -> tuple[bool, str, str]:
        """处理皮肤站授权后的重定向,返回 (成功, 标题, 详情) 用于渲染页面。"""
        if error:
            return (
                False,
                "授权未完成",
                f"皮肤站返回 {error},可回到 QQ 重新发送 /绑定。",
            )

        pending = self.oidc.pop_state(state)
        if pending is None:
            return (
                False,
                "链接已失效",
                "绑定链接超时或已被使用,请回到 QQ 重新发送 /绑定 获取新链接。",
            )
        if not code:
            return False, "回调参数不完整", "缺少授权码,请重新发起绑定。"

        try:
            token = await self.oidc.exchange_code(code)
            userinfo = await self.oidc.fetch_userinfo(token["access_token"])
        except OidcError as e:
            logger.error(f"[绑定] OIDC 流程失败: {e}")
            return (
                False,
                "绑定失败",
                "与皮肤站通信失败,请稍后重试或联系管理员。",
            )

        sub = str(userinfo.get("sub") or userinfo.get("id") or "")
        if not sub:
            return False, "绑定失败", "皮肤站未返回用户标识,请联系管理员。"

        player_name = (
            userinfo.get("minecraft_player_name")
            or userinfo.get("preferred_username")
            or ""
        )
        mc_uuid = (userinfo.get("minecraft_uuid") or "").replace("-", "").lower()
        nickname = userinfo.get("nickname") or userinfo.get("username") or ""

        binding, replaced_other = await self.store.upsert(
            qq=pending.qq,
            sub=sub,
            player_name=player_name,
            minecraft_uuid=mc_uuid,
            nickname=nickname,
        )
        shown = player_name or nickname or f"uid {sub}"
        logger.info(f"[绑定] QQ {pending.qq} <-> {shown} (sub={sub}) 绑定成功")

        # 回发确认到发起绑定的会话
        try:
            note = f"绑定成功!{_mask_qq(pending.qq)} ↔ {shown}"
            if replaced_other:
                note += (
                    f"\n该皮肤站账号原先绑定的 QQ"
                    f" {_mask_qq(replaced_other.qq)} 已被自动解绑"
                )
            await self.context.send_message(
                pending.origin, MessageChain().message(note),
            )
        except Exception as e:
            logger.warning(f"[绑定] 回发绑定确认失败: {e}")

        # 在发起绑定的群里同步群名片为角色名
        if pending.group_id and player_name:
            await self._set_group_card(
                pending.bot, pending.group_id, pending.qq, player_name,
            )

        detail = f"皮肤站账号「{shown}」已绑定到 QQ {_mask_qq(pending.qq)}。"
        if replaced_other:
            detail += "该账号此前绑定的其他 QQ 已被自动解绑。"
        return True, "绑定成功", detail

    # ==================== 入群欢迎 ====================

    async def on_group_increase(self, event: AstrMessageEvent):
        """group_increase 通知:已绑定的老朋友欢迎回来,新人引导绑定。"""
        raw = event.message_obj.raw_message
        group_id = str(raw.get("group_id", "") or "")
        user_id = str(raw.get("user_id", "") or "")
        if not group_id or not user_id:
            return
        if user_id == str(event.get_self_id()):
            return  # 机器人自己入群
        if self.watch_groups and group_id not in self.watch_groups:
            return

        binding = await self.store.get_by_qq(user_id)
        chain = MessageChain().at(name=user_id, qq=user_id)
        if binding:
            shown = binding.player_name or binding.nickname or "玩家"
            chain.message(f" 欢迎回来,{shown}喵~")
            if binding.player_name:
                await self._set_group_card(
                    getattr(event, "bot", None),
                    group_id, user_id, binding.player_name,
                )
        else:
            chain.message(
                " 欢迎加入!发送 /绑定 即可关联皮肤站账号"
                "(私聊我发送也可以)喵~"
            )
        try:
            await event.send(chain)
        except Exception as e:
            logger.warning(f"[绑定] 发送入群欢迎失败: {e}")

    async def _set_group_card(self, bot, group_id: str, qq: str, card: str):
        if not (self.auto_set_group_card and bot):
            return
        try:
            await bot.call_action(
                "set_group_card",
                group_id=int(group_id),
                user_id=int(qq),
                card=card,
            )
        except Exception as e:
            # 机器人无群管理权限时会失败,不影响绑定本身
            logger.debug(f"[绑定] 设置群名片失败: {e}")
