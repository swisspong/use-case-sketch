"""Trusted OS-user CLI; resource authorization uses existing private local storage.

No multi-user/IAM service. Each invocation creates its own Presenter/dependencies.
The administrator-controlled catalogue parser is shared with extraction.
"""

import argparse
from pathlib import Path
import sys

from ..application.model_presets import ModelPresetCatalogue
from ..application.use_cases.repair_extracted_text.request import RepairExtractedTextRequest
from ..composition import build_local_text_repair
from .extract_pdf_text_cli import _load_config
from .json_repair_cli_presenter import JsonRepairCliPresenter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose text repairs for one saved flagged parser page (no overwrite).")
    parser.add_argument("document_id")
    parser.add_argument("--page", required=True, type=int, help="One-based saved page number")
    parser.add_argument("--config", required=True, type=Path, help="Trusted administrator extraction preset catalogue")
    parser.add_argument("--preset", required=True, help="Exact configured preset name")
    parser.add_argument("--data-dir", required=True, type=Path, help="Existing private local document directory")
    parser.add_argument("--timeout-seconds", type=float, default=30, help="Socket operation timeout in (0, 300], default 30")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Positive completion token budget including provider reasoning, default 2048")
    args = parser.parse_args(argv)
    try:
        config = _load_config(args.config)
        presenter = JsonRepairCliPresenter(data_dir=args.data_dir)
        boundary = build_local_text_repair(
            catalogue=ModelPresetCatalogue(config.presets), data_dir=args.data_dir,
            output=presenter,
            timeout_seconds=args.timeout_seconds, max_tokens=args.max_tokens,
        )
        boundary.execute(RepairExtractedTextRequest(args.document_id, args.page, args.preset))
        if presenter.response is None:
            raise RuntimeError("Missing repair outcome")
        print(presenter.response)
        return presenter.exit_code
    except Exception:
        # Provider/write/presentation failures can follow a real effect. No retry.
        try:
            print('{"outcome": "error", "code": "system_error"}', file=sys.stderr)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
