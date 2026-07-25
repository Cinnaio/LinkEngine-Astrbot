"""LinkEngine AstrBot Plugin - Main entry point.

Provides bot commands for managing Minecraft server and HuskTowns towns
via the LinkEngine REST API.
"""

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import os

from .core.api_client import MCBridgeClient
from .core.permission import PermissionChecker
from .modules.server_commands import ServerCommandsModule
from .modules.husktowns_commands import HusktownsCommandsModule


@register("astrbot_plugin_mcbridge", "Cinnaio", "LinkEngine AstrBot 插件", "1.0.1")
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

    # ==================== MC 服务器命令 ====================

    @filter.command("查服")
    async def cmd_status(self, event: AstrMessageEvent):
        """/查服 - 查看服务器状态 + 在线玩家"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("[MC] 服务器模块未加载"))
            return
        result = await server_module.cmd_status([])
        await event.send(MessageChain().message(result))

    @filter.command("玩家")
    async def cmd_players(self, event: AstrMessageEvent):
        """/玩家 - 在线玩家详细列表"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("[MC] 服务器模块未加载"))
            return
        result = await server_module.cmd_players([])
        await event.send(MessageChain().message(result))

    @filter.command("在线")
    async def cmd_online(self, event: AstrMessageEvent):
        """/在线 - 在线玩家详细列表"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("[MC] 服务器模块未加载"))
            return
        result = await server_module.cmd_players([])
        await event.send(MessageChain().message(result))

    @filter.command("查")
    async def cmd_player(self, event: AstrMessageEvent, name: str = ""):
        """/查 <玩家名> - 查询指定玩家信息"""
        server_module = next((m for m in self.modules if m.name == "server"), None)
        if not server_module:
            await event.send(MessageChain().message("[MC] 服务器模块未加载"))
            return
        args = [name] if name else []
        result = await server_module.cmd_player(args)
        await event.send(MessageChain().message(result))

    # ==================== 城镇命令 ====================

    @filter.command("城镇列表")
    async def cmd_town_list(self, event: AstrMessageEvent):
        """/城镇列表 - 查看所有城镇"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("[城镇] HuskTowns 模块未加载"))
            return
        result = await town_module.cmd_list([])
        await event.send(MessageChain().message(result))

    @filter.command("查城镇")
    async def cmd_town_info(self, event: AstrMessageEvent, name: str = ""):
        """/查城镇 <城镇名> - 查看城镇详细信息"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("[城镇] HuskTowns 模块未加载"))
            return
        args = [name] if name else []
        result = await town_module.cmd_info(args)
        await event.send(MessageChain().message(result))

    @filter.command("查成员")
    async def cmd_town_members(self, event: AstrMessageEvent, name: str = ""):
        """/查成员 <城镇名> - 查看城镇成员列表"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("[城镇] HuskTowns 模块未加载"))
            return
        args = [name] if name else []
        result = await town_module.cmd_members(args)
        await event.send(MessageChain().message(result))

    @filter.command("我的城镇")
    async def cmd_my_town(self, event: AstrMessageEvent):
        """/我的城镇 - 查看自己所在城镇（需绑定）"""
        town_module = next((m for m in self.modules if m.name == "husktowns"), None)
        if not town_module:
            await event.send(MessageChain().message("[城镇] HuskTowns 模块未加载"))
            return

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
                "  /查 <玩家名> - 查询指定玩家信息\n"
                "\n"
                "HuskTowns 城镇:\n"
                "  /城镇列表 - 查看所有城镇\n"
                "  /查城镇 <城镇名> - 城镇详细信息\n"
                "  /查成员 <城镇名> - 城镇成员列表\n"
                "  /我的城镇 - 查看自己所在城镇"
            ))

    # ==================== Lifecycle ====================

    async def terminate(self):
        """Cleanup on plugin unload."""
        await self.api_client.close()
        logger.info("[LinkEngine] Plugin terminated, API client closed.")