"""Configured CLI/composition + real JSON adapters + controlled HTTP provider."""

import json
from pathlib import Path

import pytest

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


def test_cli_saves_validated_history_and_prints_only_summary_identity_and_path(
    repair_cli_files, repair_provider, monkeypatch, capsys,
):
    from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
    root, document_id, _ = repair_cli_files
    original = (root / document_id / "extraction.json").read_bytes()
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-from-env")

    assert main(arguments(repair_cli_files)) == 0

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


def test_installed_repair_console_command_points_to_v2_controller():
    from importlib.metadata import distribution
    scripts = {entry.name: entry.value for entry in distribution("registration-sketch").entry_points
               if entry.group == "console_scripts"}
    assert scripts.get("repair-extracted-text-v2") == "contexts.document_processing.v2.presentation.repair_extracted_text_cli:main"


def run_cli(files, *, module=False):
    import os
    import subprocess
    import sys
    command = ([sys.executable, "-m", "contexts.document_processing.v2.presentation.repair_extracted_text_cli"]
               if module else [str(Path(sys.executable).parent / "repair-extracted-text-v2")])
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(command + arguments(files), cwd=files[2].parent,
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


@pytest.mark.parametrize("failure", ["acknowledgement", "presentation", "stdout"])
def test_post_commit_failures_are_safe_errors_without_rollback_or_second_model_call(
    repair_cli_files, repair_provider, monkeypatch, capsys, failure,
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
    assert main(arguments(repair_cli_files)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
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
