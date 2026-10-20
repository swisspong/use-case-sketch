"""Bound multipart input before the form parser writes upload temporary files."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class UploadLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.limit = max_bytes + 64 * 1024  # multipart envelope, not PDF bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/documents"
        ):
            await self.app(scope, receive, send)
            return
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await JSONResponse(
                    {
                        "code": "file_too_large",
                        "error_code": "DOC_002",
                        "field": "file",
                    },
                    status_code=422,
                )(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        chunks.clear()
        delivered = False

        async def replay():
            nonlocal delivered, body
            if delivered:
                return await receive()
            delivered = True
            message = {"type": "http.request", "body": body, "more_body": False}
            body = b""
            return message

        await self.app(scope, replay, send)
