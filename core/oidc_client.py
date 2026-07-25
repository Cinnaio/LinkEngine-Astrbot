"""OIDC client for EnderPass (Blessing Skin OIDC Provider).

Implements the authorization code flow pieces the bot needs:
one-time state management, authorize URL building, code exchange
and userinfo fetching.
"""

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import aiohttp

STATE_TTL = 600  # 绑定链接有效期(秒)


class OidcError(Exception):
    """OIDC 流程中与皮肤站交互失败。"""


@dataclass
class PendingBind:
    """一次待完成的绑定请求,由 state 关联。"""

    qq: str
    group_id: str  # 发起绑定的群号,私聊发起时为空
    origin: str  # unified_msg_origin,绑定成功后回发确认
    bot: Any = None  # aiocqhttp 客户端,用于绑定成功后改群名片
    created_at: float = field(default_factory=time.time)


class OidcClient:
    def __init__(
        self, issuer: str, client_id: str,
        client_secret: str, redirect_uri: str,
    ):
        self.issuer = (issuer or "").rstrip("/")
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.redirect_uri = redirect_uri or ""
        self._states: dict[str, PendingBind] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def configured(self) -> bool:
        return all(
            (self.issuer, self.client_id, self.client_secret, self.redirect_uri)
        )

    @property
    def callback_path(self) -> str:
        return urlparse(self.redirect_uri).path or "/oidc/callback"

    # ---------- state 管理 ----------

    def create_state(
        self, qq: str, group_id: str, origin: str, bot: Any = None,
    ) -> str:
        self._prune()
        # 同一 QQ 重复申请时作废旧链接,保证一人只有一个有效链接
        for s in [s for s, p in self._states.items() if p.qq == qq]:
            del self._states[s]
        state = secrets.token_urlsafe(24)
        self._states[state] = PendingBind(
            qq=str(qq), group_id=str(group_id or ""), origin=origin, bot=bot,
        )
        return state

    def pop_state(self, state: str) -> Optional[PendingBind]:
        """取出并作废 state(一次性),过期返回 None。"""
        self._prune()
        return self._states.pop(state, None)

    def _prune(self):
        deadline = time.time() - STATE_TTL
        for s in [
            s for s, p in self._states.items() if p.created_at < deadline
        ]:
            del self._states[s]

    # ---------- OIDC 端点 ----------

    def build_authorize_url(self, state: str) -> str:
        query = urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
        })
        return f"{self.issuer}/oauth/authorize?{query}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def exchange_code(self, code: str) -> dict:
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.issuer}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or "access_token" not in (data or {}):
                    err = (data or {}).get("error", data)
                    raise OidcError(f"token 端点返回 {resp.status}: {err}")
                return data
        except aiohttp.ClientError as e:
            raise OidcError(f"请求 token 端点失败: {e}") from e

    async def fetch_userinfo(self, access_token: str) -> dict:
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.issuer}/oauth/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    raise OidcError(f"userinfo 端点返回 {resp.status}: {data}")
                return data or {}
        except aiohttp.ClientError as e:
            raise OidcError(f"请求 userinfo 端点失败: {e}") from e

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
