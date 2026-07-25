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
    background: linear-gradient(160deg, #f7f8fa 0%, #eceff4 100%);
    color: #23272f;
    font-family: system-ui, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
  }
  .card {
    width: min(92vw, 26rem); margin: 1rem;
    padding: 2.75rem 2.25rem 2rem;
    background: #ffffff;
    border: 1px solid #e6e8ee;
    border-radius: 16px; text-align: center;
    box-shadow: 0 10px 32px rgba(31, 41, 55, .08);
  }
  .logo {
    width: 64px; height: 64px;
    border-radius: 14px; object-fit: cover;
  }
  .brand {
    margin: .6rem 0 1.4rem; font-size: .95rem;
    letter-spacing: .04em; color: #7a8091;
  }
  .status { font-size: 2.2rem; line-height: 1; }
  h1 { font-size: 1.3rem; margin: .7rem 0 .5rem; }
  h1.ok { color: #16a34a; }
  h1.err { color: #dc2626; }
  p {
    margin: .3rem 0; color: #5c6270;
    line-height: 1.7; font-size: .95rem;
  }
  .links {
    margin-top: 1.6rem; display: flex;
    gap: .75rem; justify-content: center;
  }
  .links a {
    flex: 1; max-width: 9rem; padding: .55rem 0;
    background: #fff; border: 1px solid #d9dce3;
    border-radius: 10px; color: #3a3f4b;
    text-decoration: none; font-size: .9rem;
    transition: background .15s, border-color .15s;
  }
  .links a:hover { background: #f2f4f8; border-color: #c3c8d4; }
  .hint { margin-top: 1.4rem; font-size: .78rem; color: #9aa0ae; }
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
  <div class="links">
    <a href="https://mscraft.uk" target="_blank" rel="noopener">官网</a>
    <a href="https://skin.mscraft.uk" target="_blank" rel="noopener">皮肤站</a>
  </div>
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
