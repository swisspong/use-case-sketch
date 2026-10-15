"""Private subprocess entry point. Never extracts text or calls a provider."""

import io
import sys

from pypdf import PdfReader
from pypdf.errors import PdfReadError


def main() -> int:
    try:
        reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()), strict=True)
        if reader.is_encrypted or not len(reader.pages):
            return 1
        # Traverse page dictionaries to reject broken page references.
        for page in reader.pages:
            _ = page.mediabox
        print(len(reader.pages))
        return 0
    except (PdfReadError, ValueError, KeyError, TypeError, IndexError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
