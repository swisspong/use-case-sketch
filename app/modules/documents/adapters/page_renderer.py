import asyncio
import sys

from app.modules.documents.errors import PageRenderFailed


class LocalPageRenderer:
    """Rasterises in a subprocess so a deadline or cancellation really stops PDFium."""

    def __init__(self, timeout: float):
        self._timeout = timeout

    async def render_png(self, content: bytes, number: int) -> bytes:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modules.documents.adapters.page_render_worker",
            str(number),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(self._timeout):
                stdout, _ = await process.communicate(content)
            if process.returncode != 0 or not stdout:
                raise PageRenderFailed
            return stdout
        except TimeoutError as e:
            raise PageRenderFailed from e
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
