"""LinkEngine AstrBot Plugin - Main entry point.

Provides bot commands for managing Minecraft server and HuskTowns towns
via the LinkEngine REST API.
"""

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

from .core.api_client import MCBridgeClient
from .core.permission import PermissionChecker
from .modules.server_commands import ServerCommandsModule
from .modules.husktowns_commands import HusktownsCommandsModule


@register("astrbot_plugin_mcbridge", "Cinnaio", "LinkEngine AstrBot 插件", "1.0.0")
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

        logger.info(f"[LinkEngine] Plugin initialized. API: {self.api_url}")
        logger.info(f"[LinkEngine] Admins: {self.admins}")

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

    # ==================== MC Server Commands ====================

    @filter.command("mc")
    async def mc_command(self, event: AstrMessageEvent, sub_cmd: str = "", *args):
        """MC服务器管理命令"""
        if not sub_cmd:
            await event.send(MessageChain().message(
                "MC服务器命令:\n"
                "/mc status - 服务器状态\n"
                "/mc players - 在线玩家\n"
                "/mc player <名字> - 玩家信息\n"
                "/mc cmd <命令> - 执行命令 (管理员)\n"
                "/mc plugins - 插件列表 (管理员)"
            ))
            return

        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("[MC] 服务器模块未加载"))
            return

        resolved = server_module.resolve_alias(sub_cmd)
        for cmd_name, handler, admin_only in server_module.get_handlers():
            if cmd_name == resolved:
                if admin_only and not self._check_admin(event):
                    await event.send(MessageChain().message("[MC] 权限不足，此命令仅管理员可用"))
                    return
                result = await handler(list(args))
                await event.send(MessageChain().message(result))
                return

        await event.send(MessageChain().message(f"[MC] 未知子命令: {sub_cmd}"))

    # ==================== Town Commands ====================

    @filter.command("town")
    async def town_command(self, event: AstrMessageEvent, sub_cmd: str = "", *args):
        """HuskTowns城镇管理命令"""
        if not sub_cmd:
            await event.send(MessageChain().message(
                "城镇命令:\n"
                "/town list - 城镇列表\n"
                "/town info <名字> - 城镇信息\n"
                "/town members <名字> - 成员列表\n"
                "/town my - 我的城镇\n"
                "/town create <名字> <UUID> - 创建 (管理员)\n"
                "/town invite <城镇> <UUID> - 邀请 (管理员)\n"
                "/town kick <城镇> <UUID> - 踢出 (管理员)\n"
                "/town delete <名字> - 删除 (管理员)"
            ))
            return

        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("[城镇] HuskTowns 模块未加载"))
            return

        if sub_cmd == "my":
            user_id = self._get_user_id(event)
            uuid = self.player_bindmap.get(user_id)
            if not uuid:
                await event.send(MessageChain().message(
                    "[城镇] 你还没有绑定MC账号。\n"
                    "请联系管理员在配置中添加你的 QQ号 -> MC UUID 映射。"
                ))
                return
            resp = await self.api_client.get_player_town(uuid)
            if not resp.get("success"):
                await event.send(MessageChain().message(f"[城镇] {resp.get('message', '查询失败')}"))
                return
            data = resp.get("data", {})
            town = data.get("town", {})
            await event.send(MessageChain().message(
                f"[城镇] 你所在的城镇: {town.get('name', '未知')}\n"
                f"角色: {data.get('role', '未知')}\n"
                f"成员数: {town.get('memberCount', 0)}"
            ))
            return

        resolved = town_module.resolve_alias(sub_cmd)
        for cmd_name, handler, admin_only in town_module.get_handlers():
            if cmd_name == resolved:
                if admin_only and not self._check_admin(event):
                    await event.send(MessageChain().message("[城镇] 权限不足，此命令仅管理员可用"))
                    return
                result = await handler(list(args))
                await event.send(MessageChain().message(result))
                return

        await event.send(MessageChain().message(f"[城镇] 未知子命令: {sub_cmd}"))

    # ==================== Alias Commands ====================

    @filter.command("查服")
    async def alias_status(self, event: AstrMessageEvent):
        """/查服 - 查看服务器状态"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("[MC] 服务器模块未加载"))
            return
        result = await server_module.cmd_status([])
        await event.send(MessageChain().message(result))

    @filter.command("城镇列表")
    async def alias_town_list(self, event: AstrMessageEvent):
        """/城镇列表 - 查看所有城镇"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("[城镇] HuskTowns 模块未加载"))
            return
        result = await town_module.cmd_list([])
        await event.send(MessageChain().message(result))

    # ==================== Lifecycle ====================

    async def terminate(self):
        """Cleanup on plugin unload."""
        await self.api_client.close()
        logger.info("[LinkEngine] Plugin terminated, API client closed.")