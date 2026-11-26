import hashlib
import hmac
import os
import secrets
import time

COOKIE = "bm_session"
SESSION_SECONDS = 12 * 3600


class UiAuth:
    """Browser sessions for the interface.

    The service token is the only credential. Entering it on the login page earns a signed,
    expiring cookie, so the token itself is never stored in the browser. With no token
    configured the interface is open, like the API.
    """

    def __init__(self, token: str | None):
        self.enabled = token is not None
        self._token = (token or "").encode()
        self._key = hashlib.sha256(b"beancount-mcp-ui|" + self._token).digest() if token else os.urandom(32)

    def token_matches(self, presented: str) -> bool:
        return self.enabled and hmac.compare_digest(presented.strip().encode(), self._token)

    def issue(self) -> str:
        payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(8)}"
        return f"{payload}.{self._sign(payload)}"

    def valid(self, cookie: str | None) -> bool:
        if not self.enabled:
            return True
        if not cookie:
            return False
        payload, _, signature = cookie.rpartition(".")
        expires = payload.partition(".")[0]
        return (
            expires.isdigit()
            and int(expires) > time.time()
            and hmac.compare_digest(signature, self._sign(payload))
        )

    def csrf_token(self, cookie: str | None) -> str:
        """Tied to the session, so a form from one session is useless in another."""
        return self._sign("csrf|" + (cookie or ""))

    def _sign(self, payload: str) -> str:
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
