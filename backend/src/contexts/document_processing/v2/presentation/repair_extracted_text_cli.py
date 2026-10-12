"""Trusted OS-user CLI; resource authorization uses existing private local storage.

No multi-user/IAM service. Each invocation creates its own Presenter/dependencies.
The administrator-controlled catalogue parser is shared with extraction.
Reasoning effort is omitted unless low is explicitly requested. Opt-in diagnostics
append one allowlisted JSON line to stderr on system failure only. Outside-signal
failures include counts and at most ten code-point ranges per group, never text.
Opt-in failure logs persist these same safe facts independently of stderr. Only
system exceptions are logged; successful/expected outcomes create no log files.
Logging failure emits a safe warning without replacing the original error.
"""

import argparse
import json
from pathlib import Path
import sys

from ..application.model_presets import ModelPresetCatalogue
from ..application.use_cases.repair_extracted_text.errors import (
    InvalidRepairSourceResult, InvalidTextRepairResult, OutsideSignalsDiagnostic,
    PROPOSAL_DIAGNOSTIC_RANGE_LIMIT, RepairRunStorageError, RepairSourceError, TextRepairError,
)
from ..application.use_cases.repair_extracted_text.request import RepairExtractedTextRequest
from ..composition import build_local_repair_failure_log, build_local_text_repair
from .extract_pdf_text_cli import _load_config
from .json_repair_cli_presenter import JsonRepairCliPresenter


def _outside_signals_details(details: OutsideSignalsDiagnostic | None) -> dict[str, object] | None:
    """Select numeric facts explicitly; never serialize arbitrary metadata."""
    if not isinstance(details, OutsideSignalsDiagnostic):
        return None
    counts = (details.edit_count, details.outside_signal_edit_count, details.signal_count)
    if any(type(count) is not int or count < 0 for count in counts):
        return None
    if not 0 < details.outside_signal_edit_count <= details.edit_count or details.signal_count < 1:
        return None
    safe_ranges = []
    for ranges in (details.outside_signal_edit_ranges, details.signal_ranges):
        if not isinstance(ranges, tuple) or any(
            not isinstance(pair, tuple) or len(pair) != 2
            or any(type(position) is not int for position in pair)
            or not 0 <= pair[0] < pair[1]
            for pair in ranges
        ):
            return None
        safe_ranges.append([list(pair) for pair in ranges[:PROPOSAL_DIAGNOSTIC_RANGE_LIMIT]])
    outside_ranges, signal_ranges = safe_ranges
    return {
        "edit_count": details.edit_count,
        "outside_signal_edit_count": details.outside_signal_edit_count,
        "signal_count": details.signal_count,
        "outside_signal_edit_ranges": outside_ranges,
        "signal_ranges_sample": signal_ranges,
        "ranges_truncated": (
            len(outside_ranges) < details.outside_signal_edit_count
            or len(signal_ranges) < details.signal_count
        ),
    }


def _failure_diagnostic(error: Exception) -> dict[str, object]:
    """Allowlisted metadata only; never serialize exception/provider messages."""
    if isinstance(error, InvalidTextRepairResult):
        reason = error.reason
        if isinstance(reason, str) and reason in (
            "invalid_edits", "out_of_bounds", "outside_signals", "overlapping_edits",
        ):
            diagnostic: dict[str, object] = {"stage": "proposal_validation", "reason": reason}
            if reason == "outside_signals":
                details = _outside_signals_details(error.proposal_diagnostic)
                if details is not None:
                    diagnostic["details"] = details
            return diagnostic
        if isinstance(reason, str) and reason in (
            "incomplete_completion", "malformed_json", "invalid_schema",
        ):
            return {"stage": "model_result", "reason": reason}
        return {"stage": "model_result", "reason": "invalid_result"}
    if isinstance(error, TextRepairError):
        diagnostic = {"stage": "provider_invocation", "reason": "provider_failure"}
        if isinstance(error.reason, str) and error.reason in (
            "http_error", "timeout", "network_failure", "payload_limit", "resource_failure",
            "invalid_credentials", "invalid_endpoint",
        ):
            diagnostic["reason"] = error.reason
            if type(error.http_status) is int and 100 <= error.http_status <= 599:
                diagnostic["http_status"] = error.http_status
        return diagnostic
    if isinstance(error, RepairRunStorageError):
        return {"stage": "history", "reason": "storage_failure"}
    if isinstance(error, (RepairSourceError, InvalidRepairSourceResult)):
        return {"stage": "source", "reason": "source_failure"}
    return {"stage": "execution", "reason": "unexpected_failure"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose text repairs for one saved flagged parser page (no overwrite).")
    parser.add_argument("document_id")
    parser.add_argument("--page", required=True, type=int, help="One-based saved page number")
    parser.add_argument("--config", required=True, type=Path, help="Trusted administrator extraction preset catalogue")
    parser.add_argument("--preset", required=True, help="Exact configured preset name")
    parser.add_argument("--data-dir", required=True, type=Path, help="Existing private local document directory")
    parser.add_argument("--timeout-seconds", type=float, default=30, help="Socket operation timeout in (0, 300], default 30")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Positive completion token budget including provider reasoning, default 2048")
    parser.add_argument("--reasoning-effort", choices=("low",), default=None, help="Opt-in provider reasoning effort; omitted by default, no fallback or retry")
    parser.add_argument("--diagnostics", action="store_true", help="Append safe failure stage/reason to stderr; no source or provider text")
    parser.add_argument("--failure-log-dir", type=Path, default=None, help="Opt-in private directory for safe system-failure JSON records, separate from repair history")
    args = parser.parse_args(argv)
    try:
        config = _load_config(args.config)
        presenter = JsonRepairCliPresenter(data_dir=args.data_dir)
        boundary = build_local_text_repair(
            catalogue=ModelPresetCatalogue(config.presets), data_dir=args.data_dir,
            output=presenter,
            timeout_seconds=args.timeout_seconds, max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
        )
        boundary.execute(RepairExtractedTextRequest(args.document_id, args.page, args.preset))
        if presenter.response is None:
            raise RuntimeError("Missing repair outcome")
        print(presenter.response)
        return presenter.exit_code
    except Exception as error:
        # Provider/write/presentation failures can follow a real effect. No retry.
        diagnostic: dict[str, object] = {}
        if args.diagnostics or args.failure_log_dir is not None:
            diagnostic = _failure_diagnostic(error)
        log_failed = False
        if args.failure_log_dir is not None:
            try:
                build_local_repair_failure_log(log_dir=args.failure_log_dir).write(diagnostic=diagnostic)
            except Exception:
                # Auxiliary logging must never replace the original system error.
                log_failed = True
        try:
            print('{"outcome": "error", "code": "system_error"}', file=sys.stderr)
            if args.diagnostics:
                print(json.dumps({"diagnostic": diagnostic}), file=sys.stderr)
            if log_failed:
                print('{"warning": {"code": "failure_log_unavailable"}}', file=sys.stderr)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
