"""HuskTowns town management command module."""

from ..core.base_module import BaseCommandModule


class HusktownsCommandsModule(BaseCommandModule):
    """Provides town management commands via HuskTowns API."""

    name = "husktowns"
    required_api_module = "husktowns"

    # 命令别名映射
    aliases = {
        "城镇列表": "list",
        "列表": "list",
        "信息": "info",
        "成员": "members",
        "我的城镇": "my",
    }

    def resolve_alias(self, cmd: str) -> str:
        """Resolve command alias to actual command name."""
        return self.aliases.get(cmd, cmd)

    def get_handlers(self) -> list:
        return [
            ("list", self.cmd_list, False),
            ("info", self.cmd_info, False),
            ("members", self.cmd_members, False),
            ("my", self.cmd_my, False),
            ("create", self.cmd_create, True),
            ("invite", self.cmd_invite, True),
            ("kick", self.cmd_kick, True),
            ("delete", self.cmd_delete, True),
        ]

    async def cmd_list(self, args: list[str]) -> str:
        """查看所有城镇列表"""
        resp = await self.api.get_towns()
        if not resp.get("success"):
            return f"[城镇] {resp.get('message', '获取城镇列表失败')}"

        towns = resp.get("data", [])
        if not towns:
            return "[城镇] 当前没有城镇"

        lines = [f"城镇列表 ({len(towns)})"]
        for t in towns:
            name = t.get("name", "?")
            members = t.get("memberCount", 0)
            level = t.get("level", 0)
            money = t.get("money", 0)
            lines.append(f"  {name} | 成员: {members} | Lv.{level} | 资金: {money}")
        return "\n".join(lines)

    async def cmd_info(self, args: list[str]) -> str:
        """查看城镇信息: /town info [城镇名]"""
        if not args:
            return "[城镇] 用法: /town info <城镇名>"

        name = args[0]
        resp = await self.api.get_town(name)
        if not resp.get("success"):
            return f"[城镇] {resp.get('message', '查询失败')}"

        data = resp.get("data", {})
        members = data.get("members", [])
        greeting = data.get("greeting", "") or "无"
        farewell = data.get("farewell", "") or "无"

        lines = [
            f"城镇: {data.get('name', name)}",
            f"等级: {data.get('level', 0)}",
            f"资金: {data.get('money', 0)}",
            f"成员: {data.get('memberCount', 0)}",
            f"欢迎语: {greeting}",
            f"告别语: {farewell}",
        ]
        if members:
            lines.append("成员列表:")
            for m in members:
                online = "在线" if m.get("online") else "离线"
                lines.append(f"  {m.get('name', m.get('uuid', '?'))} [{m.get('role', 'Member')}] ({online})")
        return "\n".join(lines)

    async def cmd_members(self, args: list[str]) -> str:
        """查看城镇成员: /town members [城镇名]"""
        if not args:
            return "[城镇] 用法: /town members <城镇名>"

        name = args[0]
        resp = await self.api.get_town_members(name)
        if not resp.get("success"):
            return f"[城镇] {resp.get('message', '查询失败')}"

        members = resp.get("data", [])
        if not members:
            return f"[城镇] {name} 没有成员"

        lines = [f"{name} 成员 ({len(members)})"]
        for m in members:
            online = "在线" if m.get("online") else "离线"
            lines.append(f"  {m.get('name', '?')} [{m.get('role', 'Member')}] ({online})")
        return "\n".join(lines)

    async def cmd_my(self, args: list[str]) -> str:
        """查看自己所在城镇: /town my (需要绑定MC账号)"""
        # This requires player binding - handled in main.py
        return "[城镇] 请使用 /town bind <MC玩家名> 绑定账号后再使用此命令"

    async def cmd_create(self, args: list[str]) -> str:
        """创建城镇 (管理员): /town create <城镇名> <所有者UUID>"""
        if len(args) < 2:
            return "[城镇] 用法: /town create <城镇名> <所有者UUID>"

        town_name = args[0]
        owner_uuid = args[1]
        resp = await self.api.create_town(town_name, owner_uuid)
        if not resp.get("success"):
            return f"[城镇] 创建失败: {resp.get('message', '未知错误')}"

        return f"[城镇] 城镇 {town_name} 创建成功!"

    async def cmd_invite(self, args: list[str]) -> str:
        """邀请玩家加入城镇 (管理员): /town invite <城镇名> <玩家UUID> [角色]"""
        if len(args) < 2:
            return "[城镇] 用法: /town invite <城镇名> <玩家UUID> [角色]"

        town_name = args[0]
        player_uuid = args[1]
        role = args[2] if len(args) > 2 else "Member"

        resp = await self.api.add_town_member(town_name, player_uuid, role)
        if not resp.get("success"):
            return f"[城镇] 邀请失败: {resp.get('message', '未知错误')}"

        return f"[城镇] 已将玩家添加到 {town_name} (角色: {role})"

    async def cmd_kick(self, args: list[str]) -> str:
        """踢出城镇成员 (管理员): /town kick <城镇名> <玩家UUID>"""
        if len(args) < 2:
            return "[城镇] 用法: /town kick <城镇名> <玩家UUID>"

        town_name = args[0]
        player_uuid = args[1]

        resp = await self.api.remove_town_member(town_name, player_uuid)
        if not resp.get("success"):
            return f"[城镇] 踢出失败: {resp.get('message', '未知错误')}"

        return f"[城镇] 已将玩家从 {town_name} 移除"

    async def cmd_delete(self, args: list[str]) -> str:
        """删除城镇 (管理员): /town delete <城镇名>"""
        if not args:
            return "[城镇] 用法: /town delete <城镇名>"

        town_name = args[0]
        resp = await self.api.delete_town(town_name)
        if not resp.get("success"):
            return f"[城镇] 删除失败: {resp.get('message', '未知错误')}"

        return f"[城镇] 城镇 {town_name} 已删除"
