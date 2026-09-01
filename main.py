"""LinkEngine AstrBot Plugin - Main entry point.

Provides bot commands for managing Minecraft server and HuskTowns towns
via the LinkEngine REST API.
"""

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import asyncio
import os
import re
from pathlib import Path

from .core.api_client import MCBridgeClient
from .core.binding_store import BindingStore, format_uuid
from .core.callback_server import CallbackServer
from .core.oidc_client import OidcClient
from .core.permission import PermissionChecker
from .core.registration_notifier import RegistrationNotifier
from .modules.binding_commands import BindingModule, get_mentioned_qq
from .modules.server_commands import ServerCommandsModule
from .modules.husktowns_commands import HusktownsCommandsModule


@register("astrbot_plugin_mcbridge", "Cinnaio", "LinkEngine AstrBot 插件", "1.7.0")
class LinkEnginePlugin(Star):
    """AstrBot plugin for Minecraft server management via LinkEngine API."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context

        # Load configuration
        self.api_url = config.get("api_url", "http://127.0.0.1:8192")
        self.api_key = config.get("api_key", "change-me-to-a-random-key")
        self.admins = config.get("admins", [])
        self.player_bindmap = config.get("player_bindmap", {})

        # Initialize core components
        self.api_client = MCBridgeClient(self.api_url, self.api_key)
        self.permission = PermissionChecker(self.admins)

        # Initialize command modules
        self.modules = []
        self._register_modules()

        # 皮肤站 OIDC 账号绑定
        data_dir = self._resolve_data_dir()
        self.binding_store = BindingStore(data_dir / "bindings.db")
        self.oidc = OidcClient(
            issuer=config.get("oidc_issuer", ""),
            client_id=config.get("oidc_client_id", ""),
            client_secret=config.get("oidc_client_secret", ""),
            redirect_uri=config.get("oidc_redirect_uri", ""),
        )
        self.registration_notifier = RegistrationNotifier(
            secret=config.get("registration_webhook_secret", ""),
            groups=config.get("registration_notify_groups", []),
        )
        self.binding = BindingModule(
            store=self.binding_store,
            oidc=self.oidc,
            permission=self.permission,
            context=context,
            watch_groups=config.get("watch_groups", []),
            auto_set_group_card=config.get("auto_set_group_card", True),
        )
        self.callback_server = CallbackServer(
            host=config.get("callback_host", "0.0.0.0"),
            port=config.get("callback_port", 8193),
            path=self.oidc.callback_path,
            handler=self.binding.handle_callback,
            logo_path=Path(__file__).parent / "assets" / "logo.png",
            registration_path=config.get(
                "registration_webhook_path", "/enderpass/registration"
            ),
            registration_handler=self.registration_notifier.handle,
        )
        self._binding_started = False
        try:
            asyncio.get_running_loop().create_task(
                self._ensure_binding_started()
            )
        except RuntimeError:
            pass  # 尚无事件循环时由 initialize() 兜底启动

        logger.info(f"[LinkEngine] Plugin initialized. API: {self.api_url}")
        logger.info(f"[LinkEngine] Admins: {self.admins}")

    @staticmethod
    def _resolve_data_dir() -> Path:
        try:
            from astrbot.api.star import StarTools

            return StarTools.get_data_dir("astrbot_plugin_mcbridge")
        except Exception:
            # 旧版 AstrBot 没有 StarTools 时退回约定路径
            data_dir = Path("data/plugin_data/astrbot_plugin_mcbridge")
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir

    async def initialize(self):
        """AstrBot 插件生命周期:异步初始化。"""
        await self._ensure_binding_started()

    async def _ensure_binding_started(self):
        """启动 OAuth 回调服务(幂等)。"""
        if self._binding_started:
            return
        self._binding_started = True
        if not self.oidc.configured and not self.registration_notifier.configured:
            logger.warning(
                "[LinkEngine] 未配置皮肤站 OIDC 或 EnderPass 通知参数,相关功能不可用"
            )
            return
        try:
            await self.callback_server.start()
            logger.info(
                f"[LinkEngine] OAuth 回调服务已监听 "
                f"http://{self.callback_server.host}:{self.callback_server.port}"
                f"{self.callback_server.path}"
            )
        except Exception as e:
            logger.error(f"[LinkEngine] OAuth 回调服务启动失败: {e}")

    def _register_modules(self):
        """Register all command modules."""
        self.modules = [
            ServerCommandsModule(self.api_client, self.permission),
            HusktownsCommandsModule(self.api_client, self.permission),
        ]

    def _get_user_id(self, event: AstrMessageEvent) -> str:
        """Extract user ID from event."""
        return event.get_sender_id()

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """Check if the event sender is an admin."""
        user_id = self._get_user_id(event)
        return self.permission.is_admin(user_id)

    # ==================== MC 服务器命令 ====================

    @filter.command("查服")
    async def cmd_status(self, event: AstrMessageEvent):
        """/查服 - 查看服务器状态 + 在线玩家"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("服务器模块未加载"))
            return
        result = await server_module.cmd_status([])
        await event.send(MessageChain().message(result))

    @filter.command("玩家")
    async def cmd_players(self, event: AstrMessageEvent):
        """/玩家 - 在线玩家详细列表"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("服务器模块未加载"))
            return
        result = await server_module.cmd_players([])
        await event.send(MessageChain().message(result))

    @filter.command("在线")
    async def cmd_online(self, event: AstrMessageEvent):
        """/在线 - 在线玩家详细列表"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("服务器模块未加载"))
            return
        result = await server_module.cmd_players([])
        await event.send(MessageChain().message(result))

    @filter.command("查")
    async def cmd_player(self, event: AstrMessageEvent):
        """/查 <玩家名|@用户> - 查询指定玩家信息"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("服务器模块未加载"))
            return
        name, error = await self._resolve_player_argument(event, "查")
        if error:
            await event.send(MessageChain().message(error))
            return
        args = [name] if name else []
        result = await server_module.cmd_player(args)
        await event.send(MessageChain().message(result))

    @filter.command("余额榜")
    async def cmd_baltop(self, event: AstrMessageEvent, count: str = ""):
        """/余额榜 [数量] - 查看余额排行榜"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("服务器模块未加载"))
            return
        args = [count] if count else []
        result = await server_module.cmd_baltop(args)
        await event.send(MessageChain().message(result))

    @filter.command("广播")
    async def cmd_broadcast(self, event: AstrMessageEvent):
        """/广播 <内容> - 广播消息到服务器（管理员）"""
        if not self._check_admin(event):
            await event.send(MessageChain().message("权限不足，此命令仅管理员可用"))
            return
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("服务器模块未加载"))
            return
        # 取「广播」之后的整段原文，避免内容里的空格被逐参数拆分
        message = self._command_rest(event, "广播")
        result = await server_module.cmd_broadcast([message] if message else [])
        await event.send(MessageChain().message(result))

    # ==================== 城镇命令 ====================

    @filter.command("城镇列表")
    async def cmd_town_list(self, event: AstrMessageEvent):
        """/城镇列表 - 查看所有城镇"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("HuskTowns 模块未加载"))
            return
        result = await town_module.cmd_list([])
        await event.send(MessageChain().message(result))

    @filter.command("查城镇")
    async def cmd_town_info(self, event: AstrMessageEvent):
        """/查城镇 <城镇名|@用户> - 查看城镇详细信息"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("HuskTowns 模块未加载"))
            return
        name, error, _ = await self._resolve_town_argument(event, "查城镇")
        if error:
            await event.send(MessageChain().message(error))
            return
        args = [name] if name else []
        result = await town_module.cmd_info(args)
        await event.send(MessageChain().message(result))

    @filter.command("查成员")
    async def cmd_town_members(self, event: AstrMessageEvent):
        """/查成员 <城镇名|@用户> - 查看城镇成员列表"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("HuskTowns 模块未加载"))
            return
        name, error, _ = await self._resolve_town_argument(event, "查成员")
        if error:
            await event.send(MessageChain().message(error))
            return
        args = [name] if name else []
        result = await town_module.cmd_members(args)
        await event.send(MessageChain().message(result))

    @filter.command("我的城镇")
    async def cmd_my_town(self, event: AstrMessageEvent):
        """/我的城镇 [@用户] - 查看自己或指定用户所在城镇（需绑定）"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("HuskTowns 模块未加载"))
            return

        user_id = self._get_user_id(event)
        target_id = get_mentioned_qq(event) or user_id
        is_self_target = target_id == user_id
        uuid = None
        binding = await self.binding_store.get_by_qq(target_id)
        if binding and binding.minecraft_uuid:
            uuid = format_uuid(binding.minecraft_uuid)
        if not uuid and is_self_target:
            # 旧版手工映射兜底
            uuid = self.player_bindmap.get(user_id)
        if not uuid:
            if is_self_target:
                message = (
                    "你还没有绑定MC账号。\n"
                    "发送 /绑定 关联你的皮肤站账号后即可使用。"
                )
            else:
                message = "该用户还没有绑定MC账号。"
            await event.send(MessageChain().message(message))
            return
        resp = await self.api_client.get_player_town(uuid)
        if not resp.get("success"):
            await event.send(MessageChain().message(f"{resp.get('message', '查询失败')}"))
            return
        data = resp.get("data", {})
        town = data.get("town", {})
        subject = "你所在的城镇" if is_self_target else f"{binding.player_name if binding else '该用户'}所在的城镇"
        await event.send(MessageChain().message(
            f"{subject}: {town.get('name', '未知')}\n"
            f"角色: {data.get('role', '未知')}\n"
            f"成员数: {town.get('memberCount', 0)}"
        ))

    # ==================== 账号绑定命令 ====================

    @filter.command("绑定")
    async def cmd_bind(self, event: AstrMessageEvent):
        """/绑定 - 获取皮肤站账号绑定链接"""
        await self._ensure_binding_started()
        result = await self.binding.cmd_bind(event)
        await event.send(MessageChain().message(result))

    @filter.command("解绑")
    async def cmd_unbind(self, event: AstrMessageEvent):
        """/解绑 - 解除自己的皮肤站账号绑定"""
        result = await self.binding.cmd_unbind(event)
        await event.send(MessageChain().message(result))

    @filter.command("我的绑定")
    async def cmd_my_bind(self, event: AstrMessageEvent):
        """/我的绑定 - 查看自己的绑定信息"""
        result = await self.binding.cmd_bind_info(event)
        await event.send(MessageChain().message(result))

    @staticmethod
    def _command_rest(event: AstrMessageEvent, command: str) -> str:
        """取指令名之后的剩余文本。

        这两个管理命令不在 handler 上声明参数:@ 消息段会被展开成
        "@昵称(QQ号)" 且昵称可能含空格,AstrBot 逐参数校验会报
        "必要参数缺失/类型错误",VAR_POSITIONAL(*args)也不被支持。
        """
        text = re.sub(r"\s+", " ", (event.get_message_str() or "").strip())
        if text.startswith(command):
            text = text[len(command):]
        return text.strip()

    async def _resolve_player_argument(self, event: AstrMessageEvent, command: str):
        """将 @ 用户解析为其已绑定的 MC 角色名,普通文本保持原样。"""
        mentioned_qq = get_mentioned_qq(event)
        if not mentioned_qq:
            return self._command_rest(event, command), None

        binding = await self.binding_store.get_by_qq(mentioned_qq)
        if not binding:
            return "", "该用户还没有绑定MC账号。"
        if not binding.player_name:
            return "", "该用户没有可用的MC角色名。"
        return binding.player_name, None

    async def _resolve_town_argument(self, event: AstrMessageEvent, command: str):
        """将 @ 用户解析为其所在城镇名,普通文本保持原样。"""
        mentioned_qq = get_mentioned_qq(event)
        if not mentioned_qq:
            return self._command_rest(event, command), None, None

        binding = await self.binding_store.get_by_qq(mentioned_qq)
        if not binding:
            return "", "该用户还没有绑定MC账号。", None
        if not binding.minecraft_uuid:
            return "", "该用户没有可用的MC UUID。", binding

        resp = await self.api_client.get_player_town(format_uuid(binding.minecraft_uuid))
        if not resp.get("success"):
            return "", resp.get("message", "查询失败"), binding
        data = resp.get("data", {}) or {}
        town = data.get("town", {}) or {}
        town_name = town.get("name")
        if not town_name:
            return "", "该用户当前没有加入城镇。", binding
        return str(town_name), None, binding

    @filter.command("查绑定")
    async def cmd_bind_query(self, event: AstrMessageEvent):
        """/查绑定 <QQ号|玩家名|@用户> - 查询绑定 (管理员)"""
        if not self._check_admin(event):
            await event.send(MessageChain().message("权限不足,此命令仅管理员可用"))
            return
        target = self._command_rest(event, "查绑定")
        result = await self.binding.cmd_admin_query(event, target)
        await event.send(MessageChain().message(result))

    @filter.command("强制解绑")
    async def cmd_force_unbind(self, event: AstrMessageEvent):
        """/强制解绑 <QQ号|@用户> - 解除任意绑定 (管理员)"""
        if not self._check_admin(event):
            await event.send(MessageChain().message("权限不足,此命令仅管理员可用"))
            return
        qq = self._command_rest(event, "强制解绑")
        result = await self.binding.cmd_admin_unbind(event, qq)
        await event.send(MessageChain().message(result))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_notice_event(self, event: AstrMessageEvent):
        """监听 OneBot notice 事件:入群欢迎与绑定引导"""
        self.registration_notifier.remember_bot(getattr(event, "bot", None))
        raw = getattr(event.message_obj, "raw_message", None)
        if (
            not isinstance(raw, dict)
            or raw.get("post_type") != "notice"
            or raw.get("notice_type") != "group_increase"
        ):
            return
        await self._ensure_binding_started()
        await self.binding.on_group_increase(event)

    # ==================== 帮助命令 ====================

    @filter.command("帮助")
    async def alias_help(self, event: AstrMessageEvent):
        """/帮助 - 显示帮助信息"""
        help_image = os.path.join(os.path.dirname(__file__), "assets", "help.png")
        if os.path.exists(help_image):
            await event.send(MessageChain().file_image(help_image))
        else:
            await event.send(MessageChain().message(
                "命令帮助:\n"
                "\n"
                "MC服务器:\n"
                "  /查服 - 服务器状态 + 在线玩家\n"
                "  /玩家 或 /在线 - 在线玩家详细列表\n"
                "  /查 <玩家名> 或 @用户 - 查询玩家信息（离线也能查）\n"
                "  /余额榜 [数量] - 余额排行榜\n"
                "  /广播 <内容> - 广播到服务器（管理员）\n"
                "\n"
                "HuskTowns 城镇:\n"
                "  /城镇列表 - 查看所有城镇\n"
                "  /查城镇 <城镇名> 或 @用户 - 城镇详细信息\n"
                "  /查成员 <城镇名> 或 @用户 - 城镇成员列表\n"
                "  /我的城镇 或 /我的城镇 @用户 - 查看所在城镇\n"
                "\n"
                "账号绑定:\n"
                "  /绑定 - 绑定皮肤站账号\n"
                "  /解绑 - 解除绑定\n"
                "  /我的绑定 - 查看绑定信息"
            ))

    # ==================== Lifecycle ====================

    async def terminate(self):
        """Cleanup on plugin unload."""
        await self.callback_server.stop()
        await self.oidc.close()
        await self.api_client.close()
        logger.info("[LinkEngine] Plugin terminated, API client closed.")
