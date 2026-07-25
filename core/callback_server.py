"""Minimal aiohttp HTTP server that receives the OAuth redirect callback."""

import html
from typing import Awaitable, Callable, Optional

from aiohttp import web

# handler(state, code, error) -> (ok, title, detail)
CallbackHandler = Callable[[str, str, str], Awaitable[tuple[bool, str, str]]]

_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} - MC 账号绑定</title>
<style>
  body {{
    margin: 0; min-height: 100vh; display: flex;
    align-items: center; justify-content: center;
    background: #1e1f22; color: #e3e5e8;
    font-family: system-ui, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
  }}
  .card {{
    max-width: 26rem; margin: 1rem; padding: 2.5rem 2rem;
    background: #2b2d31; border-radius: 12px; text-align: center;
    box-shadow: 0 8px 24px rgba(0, 0, 0, .4);
  }}
  .icon {{ font-size: 3rem; }}
  h1 {{ font-size: 1.25rem; margin: 1rem 0 .5rem; }}
  p {{ margin: .25rem 0; color: #b5bac1; line-height: 1.6; }}
  .hint {{ margin-top: 1.5rem; font-size: .8rem; color: #80848e; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p>{detail}</p>
  <p class="hint">本页面无需保留,可直接关闭返回 QQ。</p>
</div>
</body>
</html>"""


class CallbackServer:
    def __init__(self, host: str, port: int, path: str,
                 handler: CallbackHandler):
        self.host = host
        self.port = int(port)
        self.path = path if path.startswith("/") else f"/{path}"
        self._handler = handler
        self._runner: Optional[web.AppRunner] = None

    @property
    def running(self) -> bool:
        return self._runner is not None

    async def start(self):
        app = web.Application()
        app.router.add_get(self.path, self._handle)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._runner = runner

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        state = request.query.get("state", "")
        code = request.query.get("code", "")
        error = request.query.get("error", "")
        ok, title, detail = await self._handler(state, code, error)
        page = _PAGE.format(
            icon="✅" if ok else "❌",
            title=html.escape(title),
            detail=html.escape(detail),
        )
        return web.Response(
            text=page,
            content_type="text/html",
            charset="utf-8",
            status=200 if ok else 400,
        )
