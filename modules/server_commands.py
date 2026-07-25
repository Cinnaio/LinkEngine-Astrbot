"""Server management command module."""

from ..core.base_module import BaseCommandModule


class ServerCommandsModule(BaseCommandModule):
    """Provides server status and player info commands."""

    name = "server"
    required_api_module = "servercore"

    def get_handlers(self) -> list:
        return [
            ("status", self.cmd_status, False),
            ("players", self.cmd_players, False),
            ("player", self.cmd_player, False),
        ]

    async def cmd_status(self, args: list[str]) -> str:
        """查看服务器状态（含在线玩家）"""
        resp = await self.api.get_server_status()
        if not resp.get("success"):
            return f"[MC] {resp.get('message', '获取状态失败')}"

        data = resp.get("data", {})
        tps = data.get("tps", {})
        player_list = data.get("playerList", [])
        online = data.get("onlinePlayers", 0)
        max_p = data.get("maxPlayers", 0)

        lines = [
            f"版本: {data.get('minecraftVersion', '未知')}",
            f"服务端: {data.get('name', '未知')} ({data.get('version', '')})",
            f"在线人数: {online}/{max_p}",
            f"TPS: {tps.get('1min', 0):.1f} / {tps.get('5min', 0):.1f} / {tps.get('15min', 0):.1f}" if isinstance(tps, dict) else f"TPS: {tps}",
            f"运行时间: {data.get('uptimeFormatted', '未知')}",
        ]

        # 在线玩家列表
        if player_list:
            lines.append("在线玩家:")
            for name in player_list:
                lines.append(f"  - {name}")
        else:
            lines.append("在线玩家: 无")

        return "\n".join(lines)

    async def cmd_players(self, args: list[str]) -> str:
        """查看在线玩家列表（详细）"""
        resp = await self.api.get_online_players()
        if not resp.get("success"):
            return f"[MC] {resp.get('message', '获取玩家列表失败')}"

        players = resp.get("data", [])
        if not players:
            return "[MC] 当前没有玩家在线"

        lines = [f"在线玩家 ({len(players)})"]
        for p in players:
            lines.append(
                f"  {p['name']} | Lv.{p.get('level', 0)} | "
                f"{p.get('gameMode', '?')} | {p.get('world', '?')} | "
                f"Ping: {p.get('ping', '?')}ms"
            )
        return "\n".join(lines)

    async def cmd_player(self, args: list[str]) -> str:
        """查询指定玩家信息: /查 <玩家名>"""
        if not args:
            return "[MC] 用法: /查 <玩家名>"

        name = args[0]
        resp = await self.api.get_player_info(name)
        if not resp.get("success"):
            return f"[MC] {resp.get('message', '查询失败')}"

        data = resp.get("data", {})
        loc = data.get("location", {})
        lines = [
            f"玩家: {data.get('name', name)}",
            f"UUID: {data.get('uuid', '未知')}",
            f"生命值: {data.get('health', 0):.1f}/{data.get('maxHealth', 20):.1f}",
            f"等级: {data.get('level', 0)} (经验: {data.get('exp', 0):.2f})",
            f"模式: {data.get('gameMode', '未知')} | 世界: {data.get('world', '未知')}",
            f"位置: ({loc.get('x', 0):.1f}, {loc.get('y', 0):.1f}, {loc.get('z', 0):.1f})",
            f"饥饿: {data.get('foodLevel', 20)}/20 | Ping: {data.get('ping', '?')}ms",
            f"OP: {'是' if data.get('isOp') else '否'} | 飞行: {'是' if data.get('isFlying') else '否'}",
        ]
        return "\n".join(lines)

