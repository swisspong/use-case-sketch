"""Configured CLI/composition + real JSON adapters + controlled HTTP provider."""

import json
from pathlib import Path

import pytest

from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import (
    InvalidTextRepairResult, TextRepairError,
)
from contexts.document_processing.v2.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v2.infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from contexts.document_processing.v2.infrastructure.local_json_repair_run_repository import LocalJsonRepairRunRepository


@pytest.fixture
def repair_cli_files(tmp_path, repair_provider):
    root = tmp_path / "documents"
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "first"), SourcePage(2, "กAข")),
        threshold_percent=100, suspicious_threshold_percent=0,
    )
    saved = LocalJsonExtractionStore(root).save(document, pdf=b"synthetic original")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"presets": [
        {"name": "unused", "endpoint": repair_provider.endpoint, "model": "unused-model",
         "api_key": "synthetic-unused-key"},
        {"name": "approved", "endpoint": repair_provider.endpoint, "model": "chosen-model",
         "api_key": "synthetic-json-key"},
    ]}))
    config.chmod(0o600)
    return root, saved.document_id, config


def arguments(files, *, preset="approved", page=2):
    root, document_id, config = files
    return [document_id, "--page", str(page), "--config", str(config),
            "--preset", preset, "--data-dir", str(root)]


@pytest.mark.parametrize("diagnostics", [False, True])
def test_cli_saves_validated_history_and_prints_only_summary_identity_and_path(
    repair_cli_files, repair_provider, monkeypatch, capsys, diagnostics,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files
    original = (root / document_id / "extraction.json").read_bytes()
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-from-env")

    assert main(arguments(repair_cli_files) + (["--diagnostics"] if diagnostics else [])) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    response = json.loads(captured.out)
    assert response["outcome"] == "suggested"
    assert response["document_id"] == document_id
    assert response["page_number"] == 2
    assert response["preset_name"] == "approved"
    assert response["model"] == "chosen-model"
    assert response["summary"] == {"edit_count": 1}
    record = LocalJsonRepairRunRepository(root).get(response["repair_id"])
    assert record.result.edits[0].replacement == "กาข"
    assert Path(response["files"]["repair_json"]) == root / "repair-runs" / record.repair_id / "record.json"
    assert (root / document_id / "extraction.json").read_bytes() == original
    assert (root / document_id / "original.pdf").read_bytes() == b"synthetic original"
    assert "กาข" not in captured.out and "\\u0e01" not in captured.out
    record_content = Path(response["files"]["repair_json"]).read_text()
    for secret in ("synthetic-from-env", "synthetic-json-key", "synthetic-unused-key"):
        assert secret not in captured.out + captured.err + record_content
    assert "api_key" not in record_content
    assert len(repair_provider.requests) == 1
    assert repair_provider.requests[0][1]["Authorization"] == "Bearer synthetic-json-key"
    assert repair_provider.requests[0][2]["model"] == "chosen-model"
    assert "synthetic-json-key" not in json.dumps(repair_provider.requests[0][2])


def test_cli_sends_explicit_token_budget_to_provider_and_records_valid_outcome(
    repair_cli_files, repair_provider, capsys,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files

    assert main(arguments(repair_cli_files) + ["--max-tokens", "4096"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    response = json.loads(captured.out)
    assert response["outcome"] == "suggested"
    assert LocalJsonRepairRunRepository(root).get(response["repair_id"]).result.document_id == document_id
    assert len(repair_provider.requests) == 1
    assert repair_provider.requests[0][2]["max_tokens"] == 4096
    assert repair_provider.requests[0][2]["model"] == "chosen-model"
    assert repair_provider.requests[0][1]["Authorization"] == "Bearer synthetic-json-key"


@pytest.mark.parametrize("module", [False, True], ids=["installed-console", "module"])
def test_cli_sends_opt_in_low_reasoning_with_explicit_budget_without_changing_source(
    repair_cli_files, repair_provider, module,
):
    root, document_id, _ = repair_cli_files
    original = (root / document_id / "extraction.json").read_bytes()

    result = run_cli(repair_cli_files, module=module, extra_args=[
        "--reasoning-effort", "low", "--max-tokens", "8192", "--diagnostics",
    ])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    response = json.loads(result.stdout)
    assert response["outcome"] == "suggested"
    assert LocalJsonRepairRunRepository(root).get(response["repair_id"]).result.document_id == document_id
    assert (root / document_id / "extraction.json").read_bytes() == original
    assert (root / document_id / "original.pdf").read_bytes() == b"synthetic original"
    assert len(repair_provider.requests) == 1
    path, headers, body = repair_provider.requests[0]
    assert path == "/v1/chat/completions"
    assert headers["Authorization"] == "Bearer synthetic-json-key"
    assert body["model"] == "chosen-model"
    assert body["max_tokens"] == 8192
    assert body["reasoning_effort"] == "low"
    assert json.loads(body["messages"][1]["content"]) == {
        "raw_text": "กAข", "spans": [{"start": 1, "end": 2, "reason": "latin_adjacent_to_thai"}],
    }


def test_provider_rejection_of_low_is_safe_failure_without_fallback_retry_or_history(
    repair_cli_files, repair_provider, capsys,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files
    original = (root / document_id / "extraction.json").read_bytes()
    repair_provider.status = 400
    repair_provider.raw_body = b"private unsupported parameter synthetic-json-key"

    assert main(arguments(repair_cli_files) + ["--reasoning-effort", "low", "--diagnostics"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": {"stage": "provider_invocation", "reason": "http_error", "http_status": 400}},
    ]
    assert len(repair_provider.requests) == 1
    assert repair_provider.requests[0][2]["reasoning_effort"] == "low"
    assert repair_provider.requests[0][2]["model"] == "chosen-model"
    assert repair_provider.requests[0][1]["Authorization"] == "Bearer synthetic-json-key"
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()
    assert (root / document_id / "extraction.json").read_bytes() == original


@pytest.mark.parametrize("budget", [0, -1])
def test_nonpositive_token_budget_is_safe_error_without_provider_or_history_effects(
    repair_cli_files, repair_provider, capsys, budget,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files

    assert main(arguments(repair_cli_files) + ["--max-tokens", str(budget)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert repair_provider.requests == []
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()


@pytest.mark.parametrize("ranges,reason", [
    (((0, 1),), "outside_signals"),
    (((1, 99),), "out_of_bounds"),
    (((0, 3), (1, 2)), "overlapping_edits"),
])
def test_opt_in_diagnostics_reports_domain_reason_without_disclosing_proposal_or_writing_history(
    repair_cli_files, repair_provider, capsys, ranges, reason,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files
    original = (root / document_id / "extraction.json").read_bytes()
    repair_provider.completion = {"outcome": "suggested", "edits": [
        {"start": start, "end": end, "replacement": "private model output synthetic-json-key"}
        for start, end in ranges
    ]}

    assert main(arguments(repair_cli_files) + ["--diagnostics"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    expected_diagnostic = {"stage": "proposal_validation", "reason": reason}
    if reason == "outside_signals":
        expected_diagnostic["details"] = {
            "edit_count": 1, "outside_signal_edit_count": 1, "signal_count": 1,
            "outside_signal_edit_ranges": [[0, 1]], "signal_ranges_sample": [[1, 2]],
            "ranges_truncated": False,
        }
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": expected_diagnostic},
    ]
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()
    assert (root / document_id / "extraction.json").read_bytes() == original
    assert len(repair_provider.requests) == 1
    request_body = repair_provider.requests[0][2]
    assert request_body["model"] == "chosen-model"
    assert repair_provider.requests[0][1]["Authorization"] == "Bearer synthetic-json-key"
    assert json.loads(request_body["messages"][1]["content"]) == {
        "raw_text": "กAข",
        "spans": [{"start": 1, "end": 2, "reason": "latin_adjacent_to_thai"}],
    }


def test_outside_signal_diagnostic_bounds_ranges_but_reports_all_rejected_edits(
    repair_cli_files, repair_provider, capsys, tmp_path,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, _, config = repair_cli_files
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "first"), SourcePage(2, "กAข" * 15)),
        threshold_percent=100, suspicious_threshold_percent=0,
    )
    saved = LocalJsonExtractionStore(root).save(document, pdf=b"synthetic original")
    original = (root / saved.document_id / "extraction.json").read_bytes()
    repair_provider.completion = {"outcome": "suggested", "edits": [
        {"start": 3 * index, "end": 3 * index + 1, "replacement": "private replacement synthetic-json-key"}
        for index in range(15)
    ]}

    log_dir = tmp_path / "failures"
    assert main(arguments((root, saved.document_id, config)) + ["--diagnostics", "--failure-log-dir", str(log_dir)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": {"stage": "proposal_validation", "reason": "outside_signals", "details": {
            "edit_count": 15, "outside_signal_edit_count": 15, "signal_count": 15,
            "outside_signal_edit_ranges": [
                [0, 1], [3, 4], [6, 7], [9, 10], [12, 13], [15, 16], [18, 19], [21, 22], [24, 25], [27, 28],
            ],
            "signal_ranges_sample": [
                [1, 2], [4, 5], [7, 8], [10, 11], [13, 14], [16, 17], [19, 20], [22, 23], [25, 26], [28, 29],
            ],
            "ranges_truncated": True,
        }}},
    ]
    log_file, = log_dir.glob("*.json")
    assert json.loads(log_file.read_text())["diagnostic"] == json.loads(captured.err.splitlines()[1])["diagnostic"]
    assert LocalJsonRepairRunRepository(root).list_by_document(saved.document_id) == ()
    assert (root / saved.document_id / "extraction.json").read_bytes() == original
    assert len(repair_provider.requests) == 1
    body = repair_provider.requests[0][2]
    assert body["model"] == "chosen-model"
    assert repair_provider.requests[0][1]["Authorization"] == "Bearer synthetic-json-key"
    source_data = json.loads(body["messages"][1]["content"])
    assert source_data["raw_text"] == "กAข" * 15
    assert len(source_data["spans"]) == 15
    assert source_data["spans"][0] == {"start": 1, "end": 2, "reason": "latin_adjacent_to_thai"}
    assert source_data["spans"][-1] == {"start": 43, "end": 44, "reason": "latin_adjacent_to_thai"}


@pytest.mark.parametrize("failure,stage,reason", [
    ("provider", "provider_invocation", "http_error"),
    ("storage", "history", "storage_failure"),
    ("source", "source", "source_failure"),
    ("truncated", "model_result", "incomplete_completion"),
    ("malformed", "model_result", "invalid_schema"),
    ("invalid_json", "model_result", "malformed_json"),
    ("outer_json", "model_result", "malformed_json"),
    ("timeout", "provider_invocation", "timeout"),
    ("network", "provider_invocation", "network_failure"),
    ("payload", "provider_invocation", "payload_limit"),
    ("resource", "provider_invocation", "resource_failure"),
])
def test_opt_in_diagnostics_classifies_declared_dependency_failure_safely(
    repair_cli_files, repair_provider, monkeypatch, capsys, failure, stage, reason,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files
    if failure == "provider":
        repair_provider.status = 503
        repair_provider.raw_body = b"private provider failure synthetic-json-key"
    elif failure == "storage":
        import os
        real_sync = os.fsync

        def sync(fd):
            if Path(os.readlink(f"/proc/self/fd/{fd}")).name == "record.json":
                raise OSError("private storage failure synthetic-json-key")
            return real_sync(fd)

        monkeypatch.setattr(os, "fsync", sync)
    elif failure == "source":
        (root / document_id / "extraction.json").write_text("private corrupt source synthetic-json-key")
    elif failure == "truncated":
        repair_provider.raw_body = json.dumps({"choices": [{
            "finish_reason": "length", "message": {"role": "assistant", "content":
                json.dumps({"outcome": "no_changes", "edits": []})},
        }]}).encode()
    elif failure == "malformed":
        repair_provider.completion = {"outcome": "suggested", "edits": []}
    elif failure == "invalid_json":
        repair_provider.raw_body = json.dumps({"choices": [{
            "finish_reason": "stop", "message": {"role": "assistant", "content":
                "private malformed JSON synthetic-json-key"},
        }]}).encode()
    elif failure == "outer_json":
        repair_provider.raw_body = b"private malformed envelope synthetic-json-key"
    elif failure == "timeout":
        from threading import Event
        repair_provider.block = Event()
    elif failure == "network":
        from http.client import HTTPConnection
        from unittest.mock import create_autospec
        connect = create_autospec(HTTPConnection.connect, side_effect=ConnectionRefusedError(
            "private network failure synthetic-json-key",
        ))
        monkeypatch.setattr(HTTPConnection, "connect", connect)
    elif failure == "payload":
        repair_provider.raw_body = b"x" * (2 * 1024 * 1024 + 1)
    elif failure == "resource":
        from http.client import HTTPConnection
        from unittest.mock import create_autospec
        send_request = create_autospec(HTTPConnection.request, side_effect=MemoryError(
            "private resource failure synthetic-json-key",
        ))
        monkeypatch.setattr(HTTPConnection, "request", send_request)

    extra_args = ["--timeout-seconds", "0.1"] if failure == "timeout" else []
    assert main(arguments(repair_cli_files) + ["--diagnostics"] + extra_args) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    expected_diagnostic = {"stage": stage, "reason": reason}
    if failure == "provider":
        expected_diagnostic["http_status"] = 503
    elif failure == "payload":
        expected_diagnostic["http_status"] = 200
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": expected_diagnostic},
    ]
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()
    assert len(repair_provider.requests) == (0 if failure in ("source", "network", "resource") else 1)
    if failure == "network":
        connect.assert_called_once()
    elif failure == "resource":
        send_request.assert_called_once()
    if repair_provider.block is not None:
        repair_provider.block.set()


@pytest.mark.parametrize("failure_logging", [False, True])
@pytest.mark.parametrize("failure,expected_diagnostic", [
    (InvalidTextRepairResult("private message synthetic-json-key", reason="private reason synthetic-json-key"),
     {"stage": "model_result", "reason": "invalid_result"}),
    (InvalidTextRepairResult("private message synthetic-json-key", reason=["private reason"]),
     {"stage": "model_result", "reason": "invalid_result"}),
    (TextRepairError("private message synthetic-json-key"),
     {"stage": "provider_invocation", "reason": "provider_failure"}),
    (TextRepairError("private message synthetic-json-key", reason="private reason", http_status=401),
     {"stage": "provider_invocation", "reason": "provider_failure"}),
    (TextRepairError("private message synthetic-json-key", reason=["private reason"], http_status=500),
     {"stage": "provider_invocation", "reason": "provider_failure"}),
    (TextRepairError("private message synthetic-json-key", reason="http_error", http_status="private status"),
     {"stage": "provider_invocation", "reason": "http_error"}),
    (TextRepairError("private message synthetic-json-key", reason="http_error", http_status=True),
     {"stage": "provider_invocation", "reason": "http_error"}),
    (TextRepairError("private message synthetic-json-key", reason="http_error", http_status=99),
     {"stage": "provider_invocation", "reason": "http_error"}),
    (TextRepairError("private message synthetic-json-key", reason="http_error", http_status=600),
     {"stage": "provider_invocation", "reason": "http_error"}),
    (TextRepairError("private message synthetic-json-key", reason="invalid_credentials"),
     {"stage": "provider_invocation", "reason": "invalid_credentials"}),
    (TextRepairError("private message synthetic-json-key", reason="invalid_endpoint"),
     {"stage": "provider_invocation", "reason": "invalid_endpoint"}),
])
def test_diagnostics_allowlist_does_not_expose_untrusted_exception_metadata(
    repair_cli_files, repair_provider, monkeypatch, capsys, failure, expected_diagnostic, failure_logging, tmp_path,
):
    from unittest.mock import ANY, create_autospec
    from contexts.document_processing.v2.application.model_presets import VisionPreset
    from contexts.document_processing.v2.domain.documents.text_quality import SuspiciousTextSpan
    from contexts.document_processing.v2.infrastructure.openai_compatible_text_repairer import OpenAICompatibleTextRepairer
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    root, document_id, _ = repair_cli_files
    propose = create_autospec(OpenAICompatibleTextRepairer.propose, side_effect=failure)
    monkeypatch.setattr(OpenAICompatibleTextRepairer, "propose", propose)
    log_dir = tmp_path / "failures"
    extra = ["--failure-log-dir", str(log_dir)] if failure_logging else []

    assert main(arguments(repair_cli_files) + ["--diagnostics"] + extra) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": expected_diagnostic},
    ]
    if failure_logging:
        log_file, = log_dir.glob("*.json")
        record = json.loads(log_file.read_text())
        assert set(record) == {"schema_version", "attempt_id", "recorded_at", "outcome", "code", "diagnostic"}
        assert record["diagnostic"] == expected_diagnostic
    else:
        assert not log_dir.exists()
    propose.assert_called_once_with(
        ANY, raw_text="กAข", spans=(SuspiciousTextSpan(1, 2, "latin_adjacent_to_thai"),),
        preset=VisionPreset("approved", repair_provider.endpoint, "chosen-model", "synthetic-json-key"),
    )
    assert repair_provider.requests == []
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()


@pytest.mark.parametrize("fault", ["unknown_metadata", "count", "range", "boolean"])
def test_outside_signal_diagnostics_omit_malformed_metadata_without_disclosing_text(
    repair_cli_files, repair_provider, monkeypatch, capsys, fault,
):
    from dataclasses import replace
    from unittest.mock import ANY, create_autospec
    from contexts.document_processing.v2.application.model_presets import VisionPreset
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import (
        InvalidTextRepairResult, OutsideSignalsDiagnostic,
    )
    from contexts.document_processing.v2.domain.documents.text_quality import SuspiciousTextSpan
    from contexts.document_processing.v2.infrastructure.openai_compatible_text_repairer import OpenAICompatibleTextRepairer
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    root, document_id, _ = repair_cli_files
    details = OutsideSignalsDiagnostic(1, 1, 1, ((0, 1),), ((1, 2),))
    if fault == "unknown_metadata":
        details = {"raw_text": "private source synthetic-json-key"}
    elif fault == "count":
        details = replace(details, edit_count="private count synthetic-json-key")
    elif fault == "range":
        details = replace(details, outside_signal_edit_ranges=((0, "private offset synthetic-json-key"),))
    elif fault == "boolean":
        details = replace(details, signal_count=True)
    failure = InvalidTextRepairResult(
        "private provider details synthetic-json-key", reason="outside_signals", proposal_diagnostic=details,
    )
    propose = create_autospec(OpenAICompatibleTextRepairer.propose, side_effect=failure)
    monkeypatch.setattr(OpenAICompatibleTextRepairer, "propose", propose)

    assert main(arguments(repair_cli_files) + ["--diagnostics"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": {"stage": "proposal_validation", "reason": "outside_signals"}},
    ]
    propose.assert_called_once_with(
        ANY, raw_text="กAข", spans=(SuspiciousTextSpan(1, 2, "latin_adjacent_to_thai"),),
        preset=VisionPreset("approved", repair_provider.endpoint, "chosen-model", "synthetic-json-key"),
    )
    assert repair_provider.requests == []
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()


def test_installed_repair_console_command_points_to_v2_controller():
    from importlib.metadata import distribution
    scripts = {entry.name: entry.value for entry in distribution("registration-sketch").entry_points
               if entry.group == "console_scripts"}
    assert scripts.get("repair-extracted-text-v2") == "contexts.document_processing.v2.presentation.repair_extracted_text_cli:main"


def run_cli(files, *, module=False, extra_args=()):
    import os
    import subprocess
    import sys
    command = ([sys.executable, "-m", "contexts.document_processing.v2.presentation.repair_extracted_text_cli"]
               if module else [str(Path(sys.executable).parent / "repair-extracted-text-v2")])
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(command + arguments(files) + list(extra_args), cwd=files[2].parent,
                          env=environment, capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("module", [False, True], ids=["installed-console", "module"])
@pytest.mark.parametrize("outcome", ["suggested", "no_changes", "unrepairable"])
def test_real_entry_points_record_each_declared_model_outcome(repair_cli_files, repair_provider, module, outcome):
    repair_provider.completion = {"outcome": outcome, "edits": (
        [{"start": 0, "end": 3, "replacement": "กาข"}] if outcome == "suggested" else []
    )}
    result = run_cli(repair_cli_files, module=module)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    response = json.loads(result.stdout)
    assert response["outcome"] == outcome
    assert response["summary"] == {"edit_count": 1 if outcome == "suggested" else 0}
    stored = json.loads(Path(response["files"]["repair_json"]).read_text())
    assert stored["outcome"] == outcome
    assert stored["repair_id"] == response["repair_id"]
    assert stored["model"] == "chosen-model"
    assert "api_key" not in stored
    assert "synthetic-json-key" not in result.stdout + result.stderr + json.dumps(stored)
    assert len(repair_provider.requests) == 1
    assert repair_provider.requests[0][1]["Authorization"] == "Bearer synthetic-json-key"
    assert repair_provider.requests[0][2]["max_tokens"] == 2048
    assert "reasoning_effort" not in repair_provider.requests[0][2]
    assert "replacement" not in result.stdout and "raw_text" not in result.stdout


@pytest.mark.parametrize("code", [
    "invalid_request", "invalid_preset", "page_not_found", "vision_page", "not_assessed", "page_not_flagged",
])
def test_every_expected_rejection_has_safe_mapping_and_no_remote_or_history_effects(
    repair_cli_files, repair_provider, monkeypatch, capsys, code,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, config = repair_cli_files
    if code in ("vision_page", "not_assessed", "page_not_flagged"):
        document = DocumentExtraction.from_pdf(
            (SourcePage(1, "first"), SourcePage(2, "กAข�" if code == "vision_page" else "กAข")),
            threshold_percent=0 if code == "vision_page" else 100,
            suspicious_threshold_percent=(None if code == "not_assessed" else
                                          100 if code == "page_not_flagged" else 0),
        )
        if code == "vision_page":
            document = document.fail_fallback(page_number=2, code="fallback_unavailable", preset_name="approved", model="chosen-model")
        document_id = LocalJsonExtractionStore(root).save(document, pdf=b"original").document_id
    files = root, document_id, config
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = arguments(files, preset="unknown" if code == "invalid_preset" else "approved",
                     page=0 if code == "invalid_request" else 99 if code == "page_not_found" else 2)
    original = (root / document_id / "extraction.json").read_bytes()
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"outcome": "rejected", "code": code}
    assert repair_provider.requests == []
    assert not (root / "repair-runs").exists()
    assert (root / document_id / "extraction.json").read_bytes() == original


@pytest.mark.parametrize("failure", [
    "provider", "malformed", "truncated", "bounds", "outside_signals", "overlap", "missing_key", "source", "config", "storage",
])
def test_system_failures_never_claim_success_disclose_details_or_publish_invalid_history(
    repair_cli_files, repair_provider, monkeypatch, capsys, failure,
):
    import os
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, config = repair_cli_files
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-env-must-not-be-used")
    if failure == "provider":
        repair_provider.status = 503
        repair_provider.raw_body = b"private provider failure"
    elif failure == "malformed":
        repair_provider.completion = {"outcome": "suggested", "edits": []}
    elif failure == "truncated":
        # Existing decoder rejects length even if the JSON would otherwise be valid.
        repair_provider.raw_body = json.dumps({"choices": [{
            "finish_reason": "length", "message": {"role": "assistant", "content":
                json.dumps({"outcome": "no_changes", "edits": []})},
        }]}).encode()
    elif failure in ("bounds", "outside_signals", "overlap"):
        edits = [{"start": 0, "end": 99 if failure == "bounds" else 1 if failure == "outside_signals" else 3,
                  "replacement": "private model output"}]
        if failure == "overlap":
            edits.append({"start": 1, "end": 2, "replacement": "other"})
        repair_provider.completion = {"outcome": "suggested", "edits": edits}
    elif failure == "missing_key":
        settings = json.loads(config.read_text())
        del settings["presets"][1]["api_key"]
        config.write_text(json.dumps(settings))
    elif failure == "source":
        (root / document_id / "extraction.json").write_text("private corrupt data")
    elif failure == "config":
        config.write_text("private malformed config")
    elif failure == "storage":
        real_sync = os.fsync
        def sync(fd):
            if Path(os.readlink(f"/proc/self/fd/{fd}")).name == "record.json":
                raise OSError("private storage failure")
            return real_sync(fd)
        monkeypatch.setattr(os, "fsync", sync)
    assert main(arguments(repair_cli_files)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()
    assert len(repair_provider.requests) == (0 if failure in ("missing_key", "source", "config") else 1)


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("failure", ["acknowledgement", "presentation", "stdout"])
def test_post_commit_failures_are_safe_errors_without_rollback_or_second_model_call(
    repair_cli_files, repair_provider, monkeypatch, capsys, failure, diagnostics, tmp_path,
):
    import builtins
    import os
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    from contexts.document_processing.v2.presentation.json_repair_cli_presenter import JsonRepairCliPresenter
    root, document_id, _ = repair_cli_files
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if failure == "acknowledgement":
        real_sync = os.fsync
        def sync(fd):
            if Path(os.readlink(f"/proc/self/fd/{fd}")).name == "repair-runs":
                raise OSError("private acknowledgement failure")
            return real_sync(fd)
        monkeypatch.setattr(os, "fsync", sync)
    elif failure == "presentation":
        def present(*args):
            raise RuntimeError("private presentation failure")
        monkeypatch.setattr(JsonRepairCliPresenter, "present", present)
    else:
        real_print = builtins.print
        def print_response(*args, **kwargs):
            if kwargs.get("file") is None:
                raise OSError("private stdout failure")
            return real_print(*args, **kwargs)
        monkeypatch.setattr(builtins, "print", print_response)
    log_dir = tmp_path / "failures"
    assert main(arguments(repair_cli_files) + ["--failure-log-dir", str(log_dir)] + (["--diagnostics"] if diagnostics else [])) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    expected_diagnostic = (
        {"stage": "history", "reason": "storage_failure"} if failure == "acknowledgement" else
        {"stage": "execution", "reason": "unexpected_failure"}
    )
    expected = [{"outcome": "error", "code": "system_error"}]
    if diagnostics:
        expected.append({"diagnostic": expected_diagnostic})
    assert [json.loads(line) for line in captured.err.splitlines()] == expected
    log_file, = log_dir.glob("*.json")
    assert json.loads(log_file.read_text())["diagnostic"] == expected_diagnostic
    record, = LocalJsonRepairRunRepository(root).list_by_document(document_id)
    assert record.result.edits[0].replacement == "กาข"
    assert len(repair_provider.requests) == 1


def test_concurrent_cli_executions_keep_presenters_identities_and_history_isolated(repair_cli_files, repair_provider):
    from concurrent.futures import ThreadPoolExecutor
    root, first_id, config = repair_cli_files
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "other"), SourcePage(2, "กAข")), threshold_percent=100, suspicious_threshold_percent=0,
    )
    second_id = LocalJsonExtractionStore(root).save(document, pdf=b"second original").document_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_cli, (root, document_id, config)) for document_id in (first_id, second_id)]
        completed = [future.result(timeout=20) for future in futures]
    responses = []
    for expected_id, result in zip((first_id, second_id), completed):
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        response = json.loads(result.stdout)
        assert response["document_id"] == expected_id
        record, = LocalJsonRepairRunRepository(root).list_by_document(expected_id)
        assert record.repair_id == response["repair_id"]
        responses.append(response)
    assert responses[0]["repair_id"] != responses[1]["repair_id"]
    assert len(repair_provider.requests) == 2


@pytest.mark.parametrize("diagnostics", [False, True])
def test_failure_log_records_safe_system_error_without_history_or_extra_stderr(
    repair_cli_files, repair_provider, tmp_path, capsys, diagnostics,
):
    from datetime import datetime, timezone
    from uuid import UUID
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    root, document_id, _ = repair_cli_files
    original = (root / document_id / "extraction.json").read_bytes()
    log_dir = tmp_path / "failures"
    repair_provider.raw_body = b"private malformed envelope synthetic-json-key"
    before = datetime.now(timezone.utc)
    extra = ["--diagnostics"] if diagnostics else []

    assert main(arguments(repair_cli_files) + ["--failure-log-dir", str(log_dir)] + extra) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    expected = [{"outcome": "error", "code": "system_error"}]
    if diagnostics:
        expected.append({"diagnostic": {"stage": "model_result", "reason": "malformed_json"}})
    assert [json.loads(line) for line in captured.err.splitlines()] == expected
    log_file, = log_dir.glob("*.json")
    record = json.loads(log_file.read_text())
    assert set(record) == {"schema_version", "attempt_id", "recorded_at", "outcome", "code", "diagnostic"}
    assert record["schema_version"] == 1
    assert UUID(record["attempt_id"]).hex == log_file.stem
    assert before <= datetime.fromisoformat(record["recorded_at"]) <= datetime.now(timezone.utc)
    assert record["outcome"] == "error" and record["code"] == "system_error"
    assert record["diagnostic"] == {"stage": "model_result", "reason": "malformed_json"}
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()
    assert (root / document_id / "extraction.json").read_bytes() == original
    assert (root / document_id / "original.pdf").read_bytes() == b"synthetic original"
    assert len(repair_provider.requests) == 1


def test_failure_log_is_private_even_with_permissive_umask(
    repair_cli_files, repair_provider, tmp_path, capsys,
):
    import os
    import stat
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    log_dir = tmp_path / "failures"
    repair_provider.status = 503
    previous = os.umask(0)
    try:
        assert main(arguments(repair_cli_files) + ["--failure-log-dir", str(log_dir)]) == 1
    finally:
        os.umask(previous)

    assert json.loads(capsys.readouterr().err) == {"outcome": "error", "code": "system_error"}
    log_file, = log_dir.glob("*.json")
    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600
    assert json.loads(log_file.read_text())["diagnostic"] == {
        "stage": "provider_invocation", "reason": "http_error", "http_status": 503,
    }


def test_failure_log_write_failure_preserves_primary_error_without_publishing_partial_record(
    repair_cli_files, repair_provider, tmp_path, monkeypatch, capsys,
):
    import os
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    root, document_id, _ = repair_cli_files
    log_dir = tmp_path / "failures"
    repair_provider.status = 503
    repair_provider.raw_body = b"private provider response synthetic-json-key"
    real_sync = os.fsync

    def sync(fd):
        if Path(os.readlink(f"/proc/self/fd/{fd}")).parent == log_dir:
            raise OSError("private logging error synthetic-json-key")
        return real_sync(fd)

    monkeypatch.setattr(os, "fsync", sync)
    assert main(arguments(repair_cli_files) + ["--diagnostics", "--failure-log-dir", str(log_dir)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": {"stage": "provider_invocation", "reason": "http_error", "http_status": 503}},
        {"warning": {"code": "failure_log_unavailable"}},
    ]
    assert list(log_dir.iterdir()) == []
    assert len(repair_provider.requests) == 1
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()


@pytest.mark.parametrize("destination", ["file", "shared_directory", "symlink"])
def test_unsafe_failure_log_destination_warns_without_replacing_primary_error_or_changing_target(
    repair_cli_files, repair_provider, tmp_path, capsys, destination,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    log_dir = tmp_path / "failures"
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    if destination == "file":
        log_dir.write_text("original target")
    elif destination == "shared_directory":
        log_dir.mkdir()
        log_dir.chmod(0o755)
    else:
        log_dir.symlink_to(target, target_is_directory=True)
    repair_provider.status = 503

    assert main(arguments(repair_cli_files) + ["--failure-log-dir", str(log_dir)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"warning": {"code": "failure_log_unavailable"}},
    ]
    assert list(target.iterdir()) == []
    if destination == "file":
        assert log_dir.read_text() == "original target"
    elif destination == "shared_directory":
        assert list(log_dir.iterdir()) == []
        assert log_dir.stat().st_mode & 0o777 == 0o755
    else:
        assert log_dir.is_symlink()
    assert len(repair_provider.requests) == 1


def test_failure_log_acknowledgement_failure_keeps_complete_record_and_original_error(
    repair_cli_files, repair_provider, tmp_path, monkeypatch, capsys,
):
    import os
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    log_dir = tmp_path / "failures"
    repair_provider.status = 503
    real_sync = os.fsync

    def sync(fd):
        if Path(os.readlink(f"/proc/self/fd/{fd}")) == log_dir:
            raise OSError("private log acknowledgement error synthetic-json-key")
        return real_sync(fd)

    monkeypatch.setattr(os, "fsync", sync)
    assert main(arguments(repair_cli_files) + ["--failure-log-dir", str(log_dir)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"warning": {"code": "failure_log_unavailable"}},
    ]
    log_file, = log_dir.iterdir()
    assert log_file.suffix == ".json"
    assert json.loads(log_file.read_text())["diagnostic"] == {
        "stage": "provider_invocation", "reason": "http_error", "http_status": 503,
    }
    assert len(repair_provider.requests) == 1


@pytest.mark.parametrize("terminal", ["no_opt_in", "success", "expected_rejection"])
def test_failure_logging_does_not_add_effects_without_opt_in_or_on_non_system_outcomes(
    repair_cli_files, repair_provider, tmp_path, capsys, terminal,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    root, document_id, _ = repair_cli_files
    log_dir = tmp_path / "failures"
    if terminal == "no_opt_in":
        repair_provider.status = 503
    extra = [] if terminal == "no_opt_in" else ["--failure-log-dir", str(log_dir)]
    page = 0 if terminal == "expected_rejection" else 2

    assert main(arguments(repair_cli_files, page=page) + extra) == {
        "no_opt_in": 1, "success": 0, "expected_rejection": 2,
    }[terminal]

    captured = capsys.readouterr()
    if terminal == "no_opt_in":
        assert captured.out == ""
        assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    else:
        assert captured.err == ""
        response = json.loads(captured.out)
        if terminal == "expected_rejection":
            assert response == {"outcome": "rejected", "code": "invalid_request"}
        else:
            assert response["outcome"] == "suggested"
    assert not log_dir.exists()
    assert len(repair_provider.requests) == (0 if terminal == "expected_rejection" else 1)
    assert len(LocalJsonRepairRunRepository(root).list_by_document(document_id)) == (1 if terminal == "success" else 0)


@pytest.mark.parametrize("module", [False, True], ids=["installed-console", "module"])
def test_real_entry_points_persist_only_safe_failed_attempts(
    repair_cli_files, repair_provider, tmp_path, module,
):
    log_dir = tmp_path / "failures"
    repair_provider.status = 503
    repair_provider.raw_body = b"private HTTP response synthetic-json-key"

    result = run_cli(repair_cli_files, module=module, extra_args=[
        "--diagnostics", "--failure-log-dir", str(log_dir),
    ])

    assert result.returncode == 1
    assert result.stdout == ""
    assert [json.loads(line) for line in result.stderr.splitlines()] == [
        {"outcome": "error", "code": "system_error"},
        {"diagnostic": {"stage": "provider_invocation", "reason": "http_error", "http_status": 503}},
    ]
    log_file, = log_dir.glob("*.json")
    assert json.loads(log_file.read_text())["diagnostic"] == {
        "stage": "provider_invocation", "reason": "http_error", "http_status": 503,
    }
    root, document_id, _ = repair_cli_files
    assert LocalJsonRepairRunRepository(root).list_by_document(document_id) == ()
    assert len(repair_provider.requests) == 1


def test_failure_log_survives_unavailable_stderr_without_retry(
    repair_cli_files, repair_provider, tmp_path, monkeypatch,
):
    import builtins
    import sys
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main

    log_dir = tmp_path / "failures"
    repair_provider.status = 503
    real_print = builtins.print

    def print_response(*args, **kwargs):
        if kwargs.get("file") is sys.stderr:
            raise OSError("private stderr failure synthetic-json-key")
        return real_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", print_response)
    assert main(arguments(repair_cli_files) + ["--failure-log-dir", str(log_dir), "--diagnostics"]) == 1

    log_file, = log_dir.glob("*.json")
    assert json.loads(log_file.read_text())["diagnostic"] == {
        "stage": "provider_invocation", "reason": "http_error", "http_status": 503,
    }
    assert len(repair_provider.requests) == 1


def test_concurrent_failure_log_identity_collision_never_overwrites_or_leaves_partial_records(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import os
    from threading import Barrier
    from unittest.mock import create_autospec
    from uuid import UUID
    from contexts.document_processing.v2.composition import build_local_repair_failure_log
    from contexts.document_processing.v2.infrastructure import local_json_repair_failure_log as logging_adapter

    identity = UUID("11111111-1111-4111-8111-111111111111")
    identities = create_autospec(logging_adapter.uuid4, return_value=identity)
    monkeypatch.setattr(logging_adapter, "uuid4", identities)
    barrier = Barrier(2)
    real_link = os.link

    def publish(*args, **kwargs):
        barrier.wait(timeout=5)
        return real_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", create_autospec(os.link, side_effect=publish))
    log_dir = tmp_path / "failures"

    def record_failure(status):
        try:
            build_local_repair_failure_log(log_dir=log_dir).write(diagnostic={
                "stage": "provider_invocation", "reason": "http_error", "http_status": status,
            })
        except FileExistsError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(record_failure, status) for status in (503, 429)]
        results = [future.result(timeout=10) for future in futures]

    assert sorted(results) == [False, True]
    log_file, = log_dir.iterdir()
    assert log_file.name == "11111111111141118111111111111111.json"
    record = json.loads(log_file.read_text())
    assert record["attempt_id"] == "11111111111141118111111111111111"
    assert record["diagnostic"] == {
        "stage": "provider_invocation", "reason": "http_error",
        "http_status": (503, 429)[results.index(True)],
    }
    assert identities.call_count == 2
