"""Local CLI controller for user-triggered OCR and its safe outer error handler.

Trusted OS-user CLI over private local storage; no HTTP server or multi-user IAM.
The caller chooses only a document id, an approved preset name and optional pages.
Endpoint/model/api_key come solely from the administrator-controlled config file.
stdout carries only the Presenter summary, never OCR text or credentials.
"""

import argparse
import logging
import os
from pathlib import Path
import sys

from ..application.model_presets import VisionPreset
from ..application.use_cases.ocr_document_pages.configuration import OcrConfig
from ..application.use_cases.ocr_document_pages.errors import InvalidOcrConfiguration
from ..application.use_cases.ocr_document_pages.request import OcrDocumentPagesRequest
from ..composition import build_local_ocr
from ..infrastructure.private_json_files import read_json
from .json_ocr_cli_presenter import JsonOcrCliPresenter


def _load_config(path: Path) -> OcrConfig:
    """Read `presets` from the shared private JSON config (thresholds are ignored).

    Same owner-only, no-final-symlink, strict, bounded parser as extraction.
    A missing api_key stays "" so the catalogue rejects it; no default/env key.
    """
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            data = read_json(directory_fd, path.name)
        finally:
            os.close(directory_fd)
        if not isinstance(data, dict) or not isinstance(data.get("presets"), list):
            raise TypeError("Expected presets list")
        return OcrConfig(tuple(
            VisionPreset(preset["name"], preset["endpoint"], preset["model"], preset.get("api_key", ""))
            for preset in data["presets"]
        ))
    except (OSError, KeyError, TypeError, ValueError, AttributeError, RecursionError):
        raise InvalidOcrConfiguration("Invalid OCR configuration file") from None


def _page_numbers(value: str) -> tuple[int, ...]:
    """'' -> () (domain rejects as no_pages_selected); '3,1' -> (3, 1)."""
    if value == "":
        return ()
    parts = value.split(",")
    if not all(part.strip().isdecimal() for part in parts):
        raise argparse.ArgumentTypeError("expected comma-separated page numbers")
    return tuple(int(part) for part in parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(
        "OCR pages of a saved v3 document with an approved vision preset and append the "
        "attempt to <data-dir>/<document_id>/ocr/. Default pages: those suggested by extraction."
    ))
    parser.add_argument("document_id")
    parser.add_argument("--preset", required=True, help="Approved preset name from the trusted config")
    parser.add_argument("--config", required=True, type=Path, help="Trusted administrator JSON with presets")
    parser.add_argument("--data-dir", required=True, type=Path, help="Private local data directory")
    parser.add_argument("--pages", type=_page_numbers, default=None,
                        help="Comma-separated one-based pages, e.g. 2,5 (may include unsuggested pages)")
    args = parser.parse_args(argv)
    logging.getLogger("pypdfium2").setLevel(logging.CRITICAL + 1)
    try:
        config = _load_config(args.config)
        presenter = JsonOcrCliPresenter(data_dir=args.data_dir)  # Per-execution output state.
        boundary = build_local_ocr(config=config, data_dir=args.data_dir, output=presenter)
        boundary.execute(OcrDocumentPagesRequest(args.document_id, args.preset, args.pages))
        if presenter.response is None:
            raise RuntimeError("Missing OCR outcome")
        print(presenter.response)
        return presenter.exit_code
    except Exception:
        # No paths, OCR text, provider details or credentials. May follow remote
        # OCR calls and/or a committed attempt file: never retry automatically.
        try:
            print('{"outcome": "error", "code": "system_error"}', file=sys.stderr)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
