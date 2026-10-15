import asyncio
import sys

from app.modules.documents.errors import PdfUnreadable, ProcessingTimeout


class LocalPdfInspector:
    async def page_count(self, content: bytes, timeout: float) -> int:
        # Isolate parsing so deadline/cancellation can actually stop CPU work.
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modules.documents.adapters.pdf_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(timeout):
                stdout, _ = await process.communicate(content)
            if process.returncode != 0:
                raise PdfUnreadable(field="file")
            return int(stdout)
        except TimeoutError as e:
            raise ProcessingTimeout(field="file") from e
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
