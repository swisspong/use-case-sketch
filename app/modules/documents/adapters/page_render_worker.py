"""Private, killable subprocess: rasterise one 1-based PDF page to PNG (stdin PDF, stdout PNG)."""

import io
import sys

import pypdfium2 as pdfium

DPI = 200
MAX_SIDE_PIXELS = 2000


def main() -> int:
    number = int(sys.argv[1])
    try:
        document = pdfium.PdfDocument(sys.stdin.buffer.read())
    except pdfium.PdfiumError:
        return 1
    try:
        if not 1 <= number <= len(document):
            return 1
        page = document[number - 1]
        width, height = page.get_size()
        scale = min(DPI / 72, MAX_SIDE_PIXELS / max(width, height, 1))
        bitmap = page.render(scale=scale)
        with io.BytesIO() as buffer:
            bitmap.to_pil().save(buffer, format="PNG")
            sys.stdout.buffer.write(buffer.getvalue())
        return 0
    except (pdfium.PdfiumError, OSError, ValueError):
        return 1
    finally:
        document.close()


if __name__ == "__main__":
    sys.exit(main())
