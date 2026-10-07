"""Read one immutable extraction JSON snapshot; do not recreate extraction policy."""

from pathlib import Path

from ..application.use_cases.repair_extracted_text.errors import InvalidRepairSourceResult, RepairSourceError
from ..application.use_cases.repair_extracted_text.ports import (
    LoadedRepairPage, RepairPageLoadResult, RepairPageNotFound,
)
from ..domain.documents.extraction import PageExtraction
from ..domain.documents.text_quality import RawPageQuality, SuspiciousTextSpan
from .private_json_files import is_identity, private_directory, read_json


class LocalJsonRepairPageSource:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def load_page(self, *, document_id: str, page_number: int) -> RepairPageLoadResult:
        if not is_identity(document_id):
            return RepairPageNotFound()
        try:
            with private_directory(self.root) as root_fd:
                with private_directory(document_id, dir_fd=root_fd) as document_fd:
                    try:
                        data = read_json(document_fd, "extraction.json")
                    except FileNotFoundError:
                        raise RepairSourceError("Extraction source unavailable") from None
        except FileNotFoundError:
            return RepairPageNotFound()
        except OSError:
            raise RepairSourceError("Extraction source unavailable") from None
        except (ValueError, TypeError):
            raise InvalidRepairSourceResult("Invalid extraction snapshot") from None
        try:
            if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
                    or data["schema_version"] not in (1, 2) or data.get("document_id") != document_id
                    or not isinstance(data.get("pages"), list) or not data["pages"]):
                raise ValueError("Invalid snapshot")
            pages = tuple(PageExtraction(**page) for page in data["pages"])
            if any(type(page.number) is not int or page.number != number
                   or page.status not in ("extracted", "failed")
                   or page.method not in ("pdf_text", "vision")
                   for number, page in enumerate(pages, start=1)):
                raise ValueError("Nonterminal/misbound page")
            reports = ()
            if data["schema_version"] == 2:
                raw_reports = data["raw_text_quality"]
                if not isinstance(raw_reports, list) or len(raw_reports) != len(pages):
                    raise ValueError("Missing assessment")
                reports = tuple(self._report(report) for report in raw_reports)
                if any(type(report.number) is not int or report.number != number
                       for number, report in enumerate(reports, start=1)):
                    raise ValueError("Misbound assessment")
            elif "raw_text_quality" in data:
                raise ValueError("Unsupported schema representation")
            if type(page_number) is not int or not 1 <= page_number <= len(pages):
                return RepairPageNotFound()
            return LoadedRepairPage(
                document_id, pages[page_number - 1], reports[page_number - 1] if reports else None,
            )
        except (ValueError, TypeError, KeyError):
            raise InvalidRepairSourceResult("Invalid extraction snapshot") from None

    @staticmethod
    def _report(data) -> RawPageQuality:
        if not isinstance(data, dict) or not isinstance(data.get("spans"), list):
            raise ValueError("Invalid assessment representation")
        return RawPageQuality(**{
            **data, "spans": tuple(SuspiciousTextSpan(**span) for span in data["spans"]),
        })
