"""Server management command module."""

from ..core.base_module import BaseCommandModule


class ServerCommandsModule(BaseCommandModule):
    """Provides server status and player info commands."""

    name = "server"

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
        """查询指定玩家信息: /查 <玩家名>

        优先读插件存储（离线也能查，带余额 / 游戏时长 / 封禁状态）；
        玩家在线时再补上实时的位置、血量等运行时状态。
        """
        if not args:
            return "[MC] 用法: /查 <玩家名>"

        name = args[0]
        profile_resp = await self.api.get_player_profile(name)
        if not profile_resp.get("success"):
            return f"[MC] {profile_resp.get('message', '查询失败')}"

        data = profile_resp.get("data", {})
        online = data.get("online", False)
        lines = [
            f"玩家: {data.get('name', name)}",
            f"UUID: {data.get('uuid', '未知')}",
            f"状态: {'在线' if online else '离线'}",
            f"余额: {data.get('balance', 0):.2f}",
            f"游戏时长: {self._format_playtime(data.get('playtimeMs', 0))}",
        ]
        if data.get("nickname"):
            lines.insert(1, f"昵称: {data['nickname']}")
        if data.get("banned"):
            reason = data.get("banReason") or "未填写"
            lines.append(f"封禁: 是（{reason}）")
        if data.get("muted"):
            reason = data.get("muteReason") or "未填写"
            lines.append(f"禁言: 是（{reason}）")

        # 在线玩家再补一份运行时状态
        if online:
            rt = await self.api.get_player_info(name)
            if rt.get("success"):
                rd = rt.get("data", {})
                loc = rd.get("location", {})
                lines.append(
                    f"血量: {rd.get('health', 0):.1f}/{rd.get('maxHealth', 20):.1f} | "
                    f"等级: {rd.get('level', 0)}"
                )
                lines.append(
                    f"模式: {rd.get('gameMode', '未知')} | 世界: {rd.get('world', '未知')} | "
                    f"Ping: {rd.get('ping', '?')}ms"
                )
                lines.append(
                    f"位置: ({loc.get('x', 0):.1f}, {loc.get('y', 0):.1f}, {loc.get('z', 0):.1f})"
                )
        return "\n".join(lines)

    async def cmd_baltop(self, args: list[str]) -> str:
        """余额排行榜: /余额榜 [数量]"""
        limit = 10
        if args:
            try:
                limit = max(1, min(50, int(args[0])))
            except ValueError:
                return "[MC] 用法: /余额榜 [数量]（数量为 1-50 的整数）"

        resp = await self.api.get_economy_top(limit)
        if not resp.get("success"):
            return f"[MC] {resp.get('message', '获取排行榜失败')}"

        data = resp.get("data", {}) or {}
        if not data:
            return "[MC] 暂无余额数据"

        lines = [f"余额排行榜 (前 {len(data)})"]
        for rank, (name, balance) in enumerate(data.items(), start=1):
            lines.append(f"  #{rank} {name} - {balance:.2f}")
        return "\n".join(lines)

    async def cmd_broadcast(self, args: list[str]) -> str:
        """向服务器广播: /广播 <内容>（管理员）"""
        message = " ".join(args).strip()
        if not message:
            return "[MC] 用法: /广播 <内容>"

        resp = await self.api.broadcast(message)
        if not resp.get("success"):
            return f"[MC] {resp.get('message', '广播失败')}"
        return f"[MC] 已广播: {message}"

    @staticmethod
    def _format_playtime(millis: int) -> str:
        """毫秒转「x天x小时x分钟」。"""
        if not millis or millis <= 0:
            return "0分钟"
        total_minutes = int(millis) // 60000
        days, rem = divmod(total_minutes, 1440)
        hours, minutes = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小时")
        if minutes or not parts:
            parts.append(f"{minutes}分钟")
        return "".join(parts)

