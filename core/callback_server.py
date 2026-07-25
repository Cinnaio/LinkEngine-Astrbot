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
<title>账号绑定 | 群隙 ClusterGap</title>
<style>
  body {
    margin: 0; min-height: 100vh; display: flex;
    align-items: center; justify-content: center;
    background: radial-gradient(120% 120% at 20% 0%,
                #2b2f4a 0%, #191b24 55%, #101014 100%);
    color: #e8eaf0;
    font-family: system-ui, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
  }
  .card {
    width: min(92vw, 26rem); margin: 1rem;
    padding: 2.75rem 2.25rem 2.25rem;
    background: rgba(43, 45, 55, .85);
    border: 1px solid rgba(255, 255, 255, .06);
    border-radius: 16px; text-align: center;
    box-shadow: 0 12px 40px rgba(0, 0, 0, .45);
  }
  .logo {
    width: 64px; height: 64px;
    border-radius: 14px; object-fit: cover;
  }
  .brand {
    margin: .6rem 0 1.4rem; font-size: .95rem;
    letter-spacing: .04em; color: #9aa0b4;
  }
  .status { font-size: 2.4rem; line-height: 1; }
  h1 { font-size: 1.3rem; margin: .8rem 0 .5rem; }
  h1.ok { color: #7ee2a8; }
  h1.err { color: #ff9a9a; }
  p {
    margin: .3rem 0; color: #b9bfd0;
    line-height: 1.7; font-size: .95rem;
  }
  .hint { margin-top: 1.8rem; font-size: .78rem; color: #767c90; }
</style>
</head>
<body>
<div class="card">
  <img class="logo" src="https://mscraft.uk/images/logo.png"
       alt="ClusterGap" onerror="this.style.display='none'">
  <div class="brand">账号绑定 | 群隙 ClusterGap</div>
  <div class="status">__ICON__</div>
  <h1 class="__STATE__">__TITLE__</h1>
  <p>__DETAIL__</p>
  <p class="hint">可直接关闭本页面返回 QQ 喵~</p>
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
        page = (
            _PAGE
            .replace("__ICON__", "✅" if ok else "❌")
            .replace("__STATE__", "ok" if ok else "err")
            .replace("__TITLE__", html.escape(title))
            .replace("__DETAIL__", html.escape(detail))
        )
        return web.Response(
            text=page,
            content_type="text/html",
            charset="utf-8",
            status=200 if ok else 400,
        )
