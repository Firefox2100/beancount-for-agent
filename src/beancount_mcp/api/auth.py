import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerTokenMiddleware:
    """Require `Authorization: Bearer <token>` on every HTTP request, the mounted MCP app included.

    Written as plain ASGI so streaming MCP responses are not buffered. The credential
    is checked here, at the edge, so services never see it. The token proves only
    that the caller may use the service. Who the caller is stays the `X-Actor` header.

    `exempt_prefix` is for the browser interface, which signs people in with the same token
    but keeps them in a session cookie instead.
    """

    def __init__(self, app: ASGIApp, token: str, exempt_prefix: str | None = None):
        self._app = app
        self._token = token.encode()
        self._exempt = exempt_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = scope["path"]
        if self._exempt and (path == self._exempt or path.startswith(self._exempt + "/")):
            await self._app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        scheme, _, presented = headers.get(b"authorization", b"").partition(b" ")
        if scheme.lower() == b"bearer" and hmac.compare_digest(presented.strip(), self._token):
            await self._app(scope, receive, send)
            return
        response = JSONResponse(
            {"detail": "missing or invalid bearer token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
        )
        await response(scope, receive, send)
