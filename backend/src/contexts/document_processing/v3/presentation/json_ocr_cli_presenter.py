"""Summarize OCR outcomes; never print OCR text (sensitive, untrusted) or credentials."""

import json
from pathlib import Path

from ..application.use_cases.ocr_document_pages.response import OcrAttemptSaved, OcrDocumentPagesResult


class JsonOcrCliPresenter:
    def __init__(self, *, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).absolute()
        self.response: str | None = None
        self.exit_code = 1

    def present(self, result: OcrDocumentPagesResult) -> None:
        if isinstance(result, OcrAttemptSaved):
            def numbers(status):
                return [page.number for page in result.pages if page.status == status]
            payload = {
                "outcome": "saved",
                "document_id": result.document_id,
                "attempt_id": result.attempt_id,
                "summary": {
                    "pages": [page.number for page in result.pages],
                    "extracted": numbers("extracted"),
                    "unreadable": numbers("unreadable"),
                    "ocr_unavailable": numbers("ocr_unavailable"),
                },
                "files": {"ocr_attempt_json": str(
                    self.data_dir / result.document_id / "ocr" / f"{result.attempt_id}.json"
                )},
            }
            self.exit_code = 0
        else:
            payload = {"outcome": "rejected", "code": result.code}
            self.exit_code = 2
        self.response = json.dumps(payload, ensure_ascii=True, allow_nan=False)
