"""Trusted-configuration file obligations through the actual extraction CLI boundary.

Model preset/credential obligations belong to the OCR use case (test_ocr_cli.py).
"""

from io import BytesIO
import json

from pypdf import PdfWriter
import pytest


@pytest.fixture
def configured_cli(tmp_path):
    config = tmp_path / "private-config.json"
    config.write_text(json.dumps({"unreadable_threshold_percent": 60}))
    config.chmod(0o600)
    root = tmp_path / "documents"
    from contexts.document_processing.v3.presentation.extract_pdf_text_cli import main
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with BytesIO() as buffer:
        writer.write(buffer)
        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(buffer.getvalue())

    def invoke(path=config):
        return main([str(pdf), "--config", str(path), "--data-dir", str(root)])
    return invoke, config, root


def test_config_symlink_is_rejected_without_storage_effects(configured_cli, capsys):
    invoke, config, root = configured_cli
    link = config.with_name("config-link.json")
    link.symlink_to(config)

    assert invoke(link) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert not root.exists()


# Regression coverage for the reused private-file checks/strict parser.
@pytest.mark.parametrize("failure", [
    "shared_permissions", "foreign_owner", "directory", "fifo", "oversized",
    "duplicate_key", "nonfinite",
])
def test_invalid_private_configuration_has_safe_error_and_no_effects(
    configured_cli, monkeypatch, capsys, failure,
):
    import os
    invoke, config, root = configured_cli
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
        config.write_text('{"unreadable_threshold_percent": 1, "unreadable_threshold_percent": 60}')
    else:
        config.write_text('{"unreadable_threshold_percent": NaN}')

    assert invoke() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert not root.exists()
