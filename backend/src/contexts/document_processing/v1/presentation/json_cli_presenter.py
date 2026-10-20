"""Summarize CLI outcomes without exposing extracted text on stdout."""

import json
from pathlib import Path

from ..application.use_cases.extract_pdf_text.response import (
    ExtractPdfTextResult, ExtractionSaved,
)


class JsonCliPresenter:
    def __init__(self, *, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).absolute()
        self.response: str | None = None
        self.exit_code = 1

    def present(self, result: ExtractPdfTextResult) -> None:
        if isinstance(result, ExtractionSaved):
            directory = self.data_dir / result.document_id
            payload = {
                "outcome": "saved",
                "document_id": result.document_id,
                "summary": {
                    "total_pages": len(result.pages),
                    "extracted_pages": sum(page.status == "extracted" for page in result.pages),
                    "failed_pages": sum(page.status == "failed" for page in result.pages),
                },
                "files": {
                    "original_pdf": str(directory / "original.pdf"),
                    "extraction_json": str(directory / "extraction.json"),
                },
            }
            self.exit_code = 0
        else:
            payload = {"outcome": "rejected", "code": result.code}
            self.exit_code = 2
        self.response = json.dumps(payload, ensure_ascii=True, allow_nan=False)
