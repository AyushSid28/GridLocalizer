import sys
import os

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.main import app as fastapi_app  # noqa: E402


class StripPrefixMiddleware:
    """Strip /api prefix from request paths before passing to FastAPI."""
    def __init__(self, app, prefix: str = "/api"):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path.startswith(self.prefix):
                scope["path"] = path[len(self.prefix):] or "/"
                raw = scope.get("raw_path", b"")
                if raw.startswith(self.prefix.encode()):
                    scope["raw_path"] = raw[len(self.prefix):] or b"/"
        await self.app(scope, receive, send)


app = StripPrefixMiddleware(fastapi_app, "/api")
