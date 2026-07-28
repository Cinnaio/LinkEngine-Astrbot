"""HTTP API client for LinkEngine."""

import aiohttp
import logging
from typing import Any, Optional

logger = logging.getLogger("astrbot.mcbridge")


class MCBridgeClient:
    """Async HTTP client for communicating with MCServerBridge REST API."""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self, method: str, path: str, json_data: Optional[dict] = None
    ) -> dict[str, Any]:
        """Make an HTTP request to the LinkEngine API."""
        session = await self._get_session()
        url = f"{self.api_url}{path}"

        try:
            async with session.request(method, url, json=json_data) as resp:
                data = await resp.json()
                if resp.status == 401:
                    return {"success": False, "message": "API 认证失败，请检查 API Key 配置"}
                if resp.status == 404:
                    return {"success": False, "message": "接口不存在或模块未加载"}
                return data
        except aiohttp.ClientConnectorError:
            return {
                "success": False,
                "message": f"无法连接到 MC 服务器 API ({self.api_url})，请检查服务器是否在线",
            }
        except aiohttp.ClientError as e:
            return {"success": False, "message": f"请求失败: {str(e)}"}
        except Exception as e:
            logger.exception("MCBridge API request error")
            return {"success": False, "message": f"未知错误: {str(e)}"}

    async def get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def post(self, path: str, json_data: Optional[dict] = None) -> dict[str, Any]:
        return await self._request("POST", path, json_data)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)

    # ---- Server Core API ----

    async def get_server_status(self) -> dict:
        return await self.get("/api/server/status")

    async def get_online_players(self) -> dict:
        return await self.get("/api/server/players")

    async def get_player_info(self, name: str) -> dict:
        return await self.get(f"/api/server/players/{name}")

    async def execute_command(self, command: str) -> dict:
        return await self.post("/api/server/command", {"command": command})

    async def get_plugins(self) -> dict:
        return await self.get("/api/server/plugins")

    # ---- Essentials API（读插件存储，离线玩家也能查）----

    async def get_player_profile(self, name: str) -> dict:
        """玩家档案：余额、游戏时长、封禁状态等，离线也能查。"""
        return await self.get(f"/api/essentials/players/{name}")

    async def get_economy_top(self, limit: int = 10) -> dict:
        """余额排行榜，返回 {玩家名: 余额}。"""
        return await self.get(f"/api/essentials/economy/top?limit={limit}")

    async def broadcast(self, message: str) -> dict:
        """向服务器全体在线玩家广播一条消息。"""
        return await self.post("/api/essentials/broadcast", {"message": message})

    # ---- HuskTowns API ----

    async def get_towns(self) -> dict:
        return await self.get("/api/husktowns/towns")

    async def get_town(self, name: str) -> dict:
        return await self.get(f"/api/husktowns/towns/{name}")

    async def get_town_members(self, name: str) -> dict:
        return await self.get(f"/api/husktowns/towns/{name}/members")

    async def add_town_member(self, town: str, uuid: str, role: str = "Member") -> dict:
        return await self.post(
            f"/api/husktowns/towns/{town}/members", {"uuid": uuid, "role": role}
        )

    async def remove_town_member(self, town: str, uuid: str) -> dict:
        return await self.delete(f"/api/husktowns/towns/{town}/members/{uuid}")

    async def create_town(self, name: str, owner_uuid: str) -> dict:
        return await self.post(
            "/api/husktowns/towns", {"name": name, "owner_uuid": owner_uuid}
        )

    async def delete_town(self, name: str) -> dict:
        return await self.delete(f"/api/husktowns/towns/{name}")

    async def get_player_town(self, uuid: str) -> dict:
        return await self.get(f"/api/husktowns/players/{uuid}/town")

