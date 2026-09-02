"""Signed HTTP client for the EnderPass invitation API."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp

from astrbot.api import logger


class EnderPassClient:
    """Call EnderPass invitation endpoints without exposing its database."""

    def __init__(self, base_url: str, secret: str, timeout: int = 10):
        self.base_url = str(base_url or "").rstrip("/")
        self.secret = str(secret or "").strip()
        self.timeout = max(3, min(30, int(timeout or 10)))
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.secret)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {
                "success": False,
                "error": "not_configured",
                "message": "管理员尚未配置 EnderPass 邀请 API。",
            }

        method = method.upper()
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        path_qs = f"{path}?{query}" if query else path
        body = b""
        if json_data is not None:
            body = json.dumps(
                json_data,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

        timestamp = str(int(time.time()))
        request_id = uuid.uuid4().hex
        canonical = b"\n".join(
            [
                timestamp.encode("ascii"),
                request_id.encode("ascii"),
                method.encode("ascii"),
                path_qs.encode("utf-8"),
                body,
            ]
        )
        signature = hmac.new(
            self.secret.encode("utf-8"), canonical, hashlib.sha256
        ).hexdigest()
        headers = {
            "Accept": "application/json",
            "X-EnderPass-Timestamp": timestamp,
            "X-EnderPass-Request-Id": request_id,
            "X-EnderPass-Signature": signature,
        }
        if body:
            headers["Content-Type"] = "application/json"

        try:
            session = await self._get_session()
            async with session.request(
                method,
                f"{self.base_url}{path_qs}",
                data=body or None,
                headers=headers,
            ) as response:
                payload = await response.json(content_type=None)
                if not isinstance(payload, dict):
                    return {
                        "success": False,
                        "error": "invalid_response",
                        "message": "EnderPass 返回了无法识别的数据。",
                    }
                if response.status < 200 or response.status >= 300:
                    payload.setdefault("success", False)
                    payload.setdefault("message", f"EnderPass 请求失败（{response.status}）。")
                return payload
        except aiohttp.ClientConnectorError:
            return {
                "success": False,
                "error": "connection_failed",
                "message": "无法连接到 EnderPass，请检查皮肤站地址或网络。",
            }
        except (aiohttp.ClientError, TimeoutError) as error:
            logger.warning(f"[EnderPass] 邀请 API 请求失败: {error}")
            return {
                "success": False,
                "error": "request_failed",
                "message": "请求 EnderPass 失败，请稍后重试。",
            }
        except Exception as error:
            logger.exception("[EnderPass] invitation API request error")
            return {
                "success": False,
                "error": "unknown_error",
                "message": "请求 EnderPass 时发生错误，请稍后重试。",
            }

    async def get_summary(self, uid: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/api/enderpass/invitations/summary", {"uid": uid}
        )

    async def get_history(self, uid: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/api/enderpass/invitations/history", {"uid": uid}
        )

    async def get_invitees(self, uid: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/api/enderpass/invitations/invitees", {"uid": uid}
        )

    async def get_leaderboard(self, limit: int = 10, uid: Optional[str] = None) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/enderpass/invitations/leaderboard",
            {"limit": max(1, min(100, int(limit))), "uid": uid},
        )

    async def generate_invitation(self, uid: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/enderpass/invitations",
            json_data={"uid": str(uid)},
        )

    async def revoke_invitation(self, uid: str, invitation_id: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/enderpass/invitations/{int(invitation_id)}/revoke",
            json_data={"uid": str(uid)},
        )
