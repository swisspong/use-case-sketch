"""Present recorded repair outcomes without exposing document/model text on stdout."""

import json
from pathlib import Path

from ..application.use_cases.repair_extracted_text.response import (
    RepairExtractedTextResult, RepairNoChanges, RepairRejected, RepairSuggested, RepairUnrepairable,
)


class JsonRepairCliPresenter:
    def __init__(self, *, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).absolute()
        self.response: str | None = None
        self.exit_code = 1

    def present(self, result: RepairExtractedTextResult) -> None:
        if isinstance(result, RepairRejected):
            payload = {"outcome": "rejected", "code": result.code}
            self.exit_code = 2
        elif isinstance(result, (RepairSuggested, RepairNoChanges, RepairUnrepairable)):
            if not result.repair_id:
                raise ValueError("Missing recorded repair identity")
            outcomes = {
                RepairSuggested: "suggested", RepairNoChanges: "no_changes", RepairUnrepairable: "unrepairable",
            }
            payload = {
                "outcome": outcomes[type(result)], "repair_id": result.repair_id,
                "document_id": result.document_id, "page_number": result.page_number,
                "preset_name": result.preset_name, "model": result.model,
                "summary": {"edit_count": len(result.edits) if isinstance(result, RepairSuggested) else 0},
                "files": {"repair_json": str(self.data_dir / "repair-runs" / result.repair_id / "record.json")},
            }
            self.exit_code = 0
        else:
            raise ValueError("Undeclared repair outcome")
        self.response = json.dumps(payload, ensure_ascii=True, allow_nan=False)
