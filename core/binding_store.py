"""SQLite-backed QQ <-> skin station account binding storage."""

import asyncio
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def format_uuid(value: str) -> str:
    """32 位无连字符 UUID 转标准带连字符小写格式;其余原样返回。"""
    value = (value or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return (
            f"{value[0:8]}-{value[8:12]}-{value[12:16]}"
            f"-{value[16:20]}-{value[20:32]}"
        ).lower()
    return value


@dataclass
class Binding:
    qq: str
    sub: str  # 皮肤站用户 ID(OIDC sub)
    player_name: str
    minecraft_uuid: str  # 32 位无连字符,可能为空
    nickname: str
    bound_at: str
    updated_at: str


def _row_to_binding(row) -> Binding:
    return Binding(
        qq=row["qq"],
        sub=row["sub"],
        player_name=row["player_name"] or "",
        minecraft_uuid=row["minecraft_uuid"] or "",
        nickname=row["nickname"] or "",
        bound_at=row["bound_at"],
        updated_at=row["updated_at"],
    )


class BindingStore:
    """QQ 与皮肤站账号的绑定,双向唯一:一个 QQ 一个账号,一个账号一个 QQ。

    冲突规则:最新一次成功授权覆盖旧绑定(登录过皮肤站的人对该账号有
    最终归属权),被顶掉的旧绑定会返回给调用方用于提示。
    """

    def __init__(self, db_path: Path):
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bindings (
                qq TEXT PRIMARY KEY,
                sub TEXT NOT NULL UNIQUE,
                player_name TEXT DEFAULT '',
                minecraft_uuid TEXT DEFAULT '',
                nickname TEXT DEFAULT '',
                bound_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        return conn

    # ---------- 同步实现(在线程池中执行) ----------

    def _get_by_qq_sync(self, qq: str) -> Optional[Binding]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bindings WHERE qq = ?", (qq,)
            ).fetchone()
            return _row_to_binding(row) if row else None

    def _get_by_player_sync(self, name: str) -> Optional[Binding]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bindings WHERE player_name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            return _row_to_binding(row) if row else None

    def _upsert_sync(self, qq, sub, player_name, minecraft_uuid, nickname):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            old_qq_row = conn.execute(
                "SELECT * FROM bindings WHERE qq = ?", (qq,)
            ).fetchone()
            old_sub_row = conn.execute(
                "SELECT * FROM bindings WHERE sub = ?", (sub,)
            ).fetchone()

            # 该皮肤站账号之前绑在别的 QQ 上 -> 顶掉
            replaced_other = None
            if old_sub_row and old_sub_row["qq"] != qq:
                replaced_other = _row_to_binding(old_sub_row)

            # 同一 QQ 重新授权同一账号时保留最初绑定时间
            bound_at = now
            if old_qq_row and old_qq_row["sub"] == sub:
                bound_at = old_qq_row["bound_at"]

            conn.execute(
                "DELETE FROM bindings WHERE qq = ? OR sub = ?", (qq, sub)
            )
            conn.execute(
                "INSERT INTO bindings"
                " (qq, sub, player_name, minecraft_uuid, nickname,"
                "  bound_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (qq, sub, player_name, minecraft_uuid, nickname, bound_at, now),
            )

            binding = Binding(
                qq=qq,
                sub=sub,
                player_name=player_name,
                minecraft_uuid=minecraft_uuid,
                nickname=nickname,
                bound_at=bound_at,
                updated_at=now,
            )
            return binding, replaced_other

    def _delete_by_qq_sync(self, qq: str) -> Optional[Binding]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bindings WHERE qq = ?", (qq,)
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM bindings WHERE qq = ?", (qq,))
            return _row_to_binding(row)

    def _count_sync(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM bindings").fetchone()[0]

    # ---------- 异步接口 ----------

    async def get_by_qq(self, qq: str) -> Optional[Binding]:
        return await asyncio.to_thread(self._get_by_qq_sync, str(qq))

    async def get_by_player(self, name: str) -> Optional[Binding]:
        return await asyncio.to_thread(self._get_by_player_sync, name)

    async def upsert(
        self, qq: str, sub: str, player_name: str = "",
        minecraft_uuid: str = "", nickname: str = "",
    ):
        """写入绑定,返回 (新绑定, 被顶掉的其他QQ的旧绑定或 None)。"""
        return await asyncio.to_thread(
            self._upsert_sync, str(qq), str(sub),
            player_name, minecraft_uuid, nickname,
        )

    async def delete_by_qq(self, qq: str) -> Optional[Binding]:
        return await asyncio.to_thread(self._delete_by_qq_sync, str(qq))

    async def count(self) -> int:
        return await asyncio.to_thread(self._count_sync)
