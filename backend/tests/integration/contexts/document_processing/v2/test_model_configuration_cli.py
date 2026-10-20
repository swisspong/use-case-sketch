"""Shared trusted-configuration obligations through both actual CLI boundaries."""

from io import BytesIO
import json

from pypdf import PdfWriter
import pytest


@pytest.fixture(params=["extraction", "repair"])
def configured_cli(request, tmp_path, repair_provider):
    config = tmp_path / "private-config.json"
    config.write_text(json.dumps({"presets": [{
        "name": "approved", "endpoint": repair_provider.endpoint,
        "model": "chosen-model", "api_key": "synthetic-private-json-key",
    }]}))
    config.chmod(0o600)
    root = tmp_path / "documents"
    if request.param == "extraction":
        from contexts.document_processing.v2.presentation.extract_pdf_text_cli import main
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with BytesIO() as buffer:
            writer.write(buffer)
            pdf = tmp_path / "input.pdf"
            pdf.write_bytes(buffer.getvalue())
        positional = [str(pdf)]
    else:
        from contexts.document_processing.v2.presentation.repair_extracted_text_cli import main
        positional = ["a" * 32, "--page", "1"]

    def invoke(path=config):
        return main(positional + ["--config", str(path), "--preset", "approved",
                                  "--data-dir", str(root)])
    return invoke, config, root


def test_config_symlink_is_rejected_without_provider_or_storage_effects(
    configured_cli, repair_provider, capsys,
):
    invoke, config, root = configured_cli
    link = config.with_name("config-link.json")
    link.symlink_to(config)

    assert invoke(link) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert repair_provider.requests == []
    assert not root.exists()


# Regression coverage for the reused private-file checks/strict parser and
# catalogue validation already implemented; no manufactured red cycle.
@pytest.mark.parametrize("failure", [
    "shared_permissions", "foreign_owner", "directory", "fifo", "oversized",
    "duplicate_key", "nonfinite", "missing_key", "blank_key", "non_string_key",
    "unselected_missing_key", "env_field", "env_field_with_key",
])
def test_invalid_private_configuration_has_safe_error_and_no_effects(
    configured_cli, repair_provider, monkeypatch, capsys, failure,
):
    import os
    invoke, config, root = configured_cli
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-env-cannot-rescue-config")
    settings = json.loads(config.read_text())
    if failure == "shared_permissions":
        config.chmod(0o644)
    elif failure == "foreign_owner":
        uid = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    elif failure in ("directory", "fifo"):
        config.unlink()
        if failure == "directory":
            config.mkdir(mode=0o700)
        else:
            os.mkfifo(config, mode=0o600)
    elif failure == "oversized":
        config.write_bytes(b" " * (16 * 1024 * 1024 + 1))
    elif failure == "duplicate_key":
        config.write_text('{"presets": [], "presets": ' + json.dumps(settings["presets"]) + '}')
    elif failure == "nonfinite":
        settings["unreadable_threshold_percent"] = float("nan")
        config.write_text(json.dumps(settings))
    else:
        if failure in ("missing_key", "env_field"):
            del settings["presets"][0]["api_key"]
            if failure == "env_field":
                settings["presets"][0]["api_key_env"] = "OPENAI_API_KEY"
        elif failure == "env_field_with_key":
            settings["presets"][0]["api_key_env"] = "OPENAI_API_KEY"
        elif failure == "blank_key":
            settings["presets"][0]["api_key"] = " \t\n"
        elif failure == "non_string_key":
            settings["presets"][0]["api_key"] = 123
        else:
            settings["presets"].append({
                "name": "unused", "endpoint": repair_provider.endpoint, "model": "other",
            })
        config.write_text(json.dumps(settings))

    assert invoke() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert repair_provider.requests == []
    assert not root.exists()
