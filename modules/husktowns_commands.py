"""HuskTowns town management command module."""

from ..core.base_module import BaseCommandModule


class HusktownsCommandsModule(BaseCommandModule):
    """Provides town query commands via HuskTowns API."""

    name = "husktowns"

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
        """查看城镇信息: /查城镇 <城镇名>"""
        if not args:
            return "[城镇] 用法: /查城镇 <城镇名>"

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
        """查看城镇成员: /查成员 <城镇名>"""
        if not args:
            return "[城镇] 用法: /查成员 <城镇名>"

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


