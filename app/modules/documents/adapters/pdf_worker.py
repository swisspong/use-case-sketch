"""Private, killable subprocess: validate PDF and extract each page. No OCR."""

import io
import json
import sys

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.modules.documents.adapters.pdf_geometry import image_coverage


def main() -> int:
    try:
        reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()), strict=True)
        if reader.is_encrypted or not len(reader.pages):
            return 1
        pages = []
        for page in reader.pages:
            _ = page.mediabox
            # PostgreSQL text cannot store NUL or unpaired Unicode surrogates.
            # Preserve their positions as replacement characters for quality assessment.
            text = (page.extract_text() or "").replace("\x00", "\ufffd")
            text = "".join("\ufffd" if "\ud800" <= c <= "\udfff" else c for c in text)
            pages.append(
                {
                    "text": text,
                    "image_percent": image_coverage(page, reader),
                }
            )
        print(json.dumps(pages, ensure_ascii=True))
        return 0
    except (
        PdfReadError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        RecursionError,
        NotImplementedError,
    ):
        return 1


if __name__ == "__main__":
    sys.exit(main())
