"""Local CLI controller and safe outer error handler; no HTTP/API server."""

import argparse
import json
import logging
from pathlib import Path
import sys

from ..application.use_cases.extract_pdf_text.configuration import (
    ExtractionConfig, VisionPreset,
)
from ..application.use_cases.extract_pdf_text.errors import InvalidExtractionConfiguration
from ..application.use_cases.extract_pdf_text.request import ExtractPdfTextRequest
from ..composition import build_local_extraction
from .json_cli_presenter import JsonCliPresenter


def _load_config(path: Path) -> ExtractionConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        presets = data["presets"]
        if not isinstance(presets, list):
            raise TypeError("Expected preset list")
        return ExtractionConfig(
            tuple(VisionPreset(**preset) for preset in presets),
            unreadable_threshold_percent=data.get("unreadable_threshold_percent", 60),
            suspicious_threshold_percent=data.get("suspicious_threshold_percent"),
        )
    except (KeyError, TypeError, ValueError):
        raise InvalidExtractionConfiguration("Invalid extraction configuration file") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract PDF text into private local PDF/JSON storage (vision offline).")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--config", required=True, type=Path, help="Trusted administrator JSON preset catalogue")
    parser.add_argument("--preset", required=True, help="Exact configured preset name")
    parser.add_argument("--data-dir", required=True, type=Path, help="Private local data directory; parent must exist")
    args = parser.parse_args(argv)
    # Library diagnostics can contain input fragments. The CLI never emits them.
    logging.getLogger("pypdf").setLevel(logging.CRITICAL + 1)
    try:
        config = _load_config(args.config)
        presenter = JsonCliPresenter(data_dir=args.data_dir)  # Per-execution output state.
        boundary = build_local_extraction(config=config, data_dir=args.data_dir, output=presenter)
        boundary.execute(ExtractPdfTextRequest(args.pdf.read_bytes(), args.preset))
        if presenter.response is None:
            raise RuntimeError("Missing extraction outcome")
        print(presenter.response)
        return presenter.exit_code
    except Exception:
        # Do not expose paths, PDF/text, configuration secrets or provider errors.
        # This may follow a commit, including a failed stdout write: never retry.
        try:
            print('{"outcome": "error", "code": "system_error"}', file=sys.stderr)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
