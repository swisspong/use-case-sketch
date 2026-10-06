"""PDF library translation only; page quality decisions belong to the domain."""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import DependencyError, LimitReachedError, ParseError, PdfReadError

from ..application.use_cases.extract_pdf_text.errors import PdfExtractionError
from ..application.use_cases.extract_pdf_text.ports import (
    ParsedPdf, PdfParseResult, PdfRejected,
)
from ..domain.documents.extraction import SourcePage


class PypdfTextExtractor:
    def extract(self, pdf: bytes) -> PdfParseResult:
        if not pdf.startswith(b"%PDF-"):
            return PdfRejected("invalid_pdf")
        try:
            with BytesIO(pdf) as stream:
                try:
                    reader = PdfReader(stream, strict=True)
                except (NotImplementedError, DependencyError):
                    # Constructor-only failures: unsupported encryption/crypto.
                    return PdfRejected("encrypted_pdf")
                if reader.is_encrypted:
                    return PdfRejected("encrypted_pdf")
                return ParsedPdf(tuple(
                    SourcePage(number, page.extract_text())
                    for number, page in enumerate(reader.pages, start=1)
                ))
        except (PdfReadError, ParseError):
            return PdfRejected("invalid_pdf")
        except (MemoryError, LimitReachedError):
            raise PdfExtractionError("PDF extraction unavailable") from None
