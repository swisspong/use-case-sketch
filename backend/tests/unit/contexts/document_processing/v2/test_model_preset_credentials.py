"""Shared credential obligations through both real use-case Input Boundaries.

These unit tests do not prove HTTP Authorization or filesystem secrecy;
separate integration suites cover the real config loader, CLI and HTTP adapter.
"""

from dataclasses import asdict, replace
import json
from pathlib import Path
from unittest.mock import create_autospec

import pytest

from contexts.document_processing.v2.application.model_presets import (
    InvalidModelPresetCatalogue, ModelPresetCatalogue, VisionPreset,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.configuration import ExtractionConfig
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.errors import InvalidExtractionConfiguration
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.input_boundary import ExtractPdfTextInputBoundary
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.interactor import ExtractPdfTextInteractor
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.output_boundary import ExtractPdfTextOutputBoundary
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.ports import (
    ExtractionStore, FallbackExtractor, ParsedPdf, PdfTextExtractor, SavedDocument, VisionText,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.request import ExtractPdfTextRequest
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.input_boundary import RepairExtractedTextInputBoundary
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.interactor import RepairExtractedTextInteractor
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.output_boundary import RepairExtractedTextOutputBoundary
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import (
    LoadedRepairPage, RepairPageSource, RepairRunRepository, TextRepairer, TextRepairNoChanges,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.records import SavedRepairRun
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.request import RepairExtractedTextRequest
from contexts.document_processing.v2.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v2.domain.documents.text_quality import SuspiciousTextSpan


@pytest.fixture(params=["extraction", "repair"])
def consumer(request):
    def build(presets):
        if request.param == "extraction":
            facts = create_autospec(PdfTextExtractor, instance=True)
            model = create_autospec(FallbackExtractor, instance=True)
            store = create_autospec(ExtractionStore, instance=True)
            output = create_autospec(ExtractPdfTextOutputBoundary, instance=True)
            facts.extract.return_value = ParsedPdf((SourcePage(1, ""),))
            model.extract_page.return_value = VisionText("Recovered page")
            store.save.return_value = SavedDocument("document-92")
            boundary: ExtractPdfTextInputBoundary = ExtractPdfTextInteractor(
                pdf_extractor=facts, fallback=model, store=store, output=output,
                config=ExtractionConfig(presets),
            )
            invocation = ExtractPdfTextRequest(b"%PDF-credential-test", "selected")
            failure = InvalidExtractionConfiguration
        else:
            facts = create_autospec(RepairPageSource, instance=True)
            model = create_autospec(TextRepairer, instance=True)
            store = create_autospec(RepairRunRepository, instance=True)
            output = create_autospec(RepairExtractedTextOutputBoundary, instance=True)
            document = DocumentExtraction.from_pdf(
                (SourcePage(1, "ทีC"),), threshold_percent=60,
                suspicious_threshold_percent=0,
            )
            assert isinstance(document, DocumentExtraction)
            facts.load_page.return_value = LoadedRepairPage(
                "document-92", document.pages[0], document.raw_text_quality[0],
            )
            model.propose.return_value = TextRepairNoChanges()
            store.save.return_value = SavedRepairRun("repair-92")
            boundary: RepairExtractedTextInputBoundary = RepairExtractedTextInteractor(
                source=facts, repairer=model, repository=store, output=output,
                catalogue=ModelPresetCatalogue(presets),
            )
            invocation = RepairExtractedTextRequest("document-92", 1, "selected")
            failure = InvalidModelPresetCatalogue
        return boundary, invocation, facts, model, store, output, failure
    return build


def test_missing_preset_api_key_is_configuration_failure_before_any_io(consumer):
    preset = VisionPreset("selected", "https://selected.example/v1", "selected-model")
    boundary, request, facts, model, store, output, failure = consumer((preset,))

    with pytest.raises(failure):
        boundary.execute(request)

    assert facts.mock_calls == []
    assert model.mock_calls == []
    store.save.assert_not_called()
    output.present.assert_not_called()


# Tests of the validation and preset forwarding already present above; no
# artificial red. Domain logic stays real; only dependency/output ports are mocks.
@pytest.mark.parametrize("key", ["", " \t\n", None, False, 123, ["synthetic-key"]])
def test_blank_or_non_string_api_key_fails_before_any_io(consumer, key):
    preset = VisionPreset("selected", "https://selected.example/v1", "selected-model", key)
    boundary, request, facts, model, store, output, failure = consumer((preset,))

    with pytest.raises(failure):
        boundary.execute(request)

    assert facts.mock_calls == []
    assert model.mock_calls == []
    store.save.assert_not_called()
    output.present.assert_not_called()


def test_environment_key_does_not_replace_missing_json_key(consumer, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-key")
    presets = (VisionPreset("selected", "https://selected.example/v1", "selected-model"),)
    boundary, request, facts, model, store, output, failure = consumer(presets)

    with pytest.raises(failure):
        boundary.execute(request)

    assert facts.mock_calls == []
    assert model.mock_calls == []
    store.save.assert_not_called()
    output.present.assert_not_called()


def test_unselected_preset_also_requires_a_key(consumer):
    presets = (
        VisionPreset("unused", "https://unused.example/v1", "unused-model"),
        VisionPreset("selected", "https://selected.example/v1", "selected-model", "synthetic-selected-key"),
    )
    boundary, request, facts, model, store, output, failure = consumer(presets)

    with pytest.raises(failure):
        boundary.execute(request)

    assert facts.mock_calls == []
    assert model.mock_calls == []
    store.save.assert_not_called()
    output.present.assert_not_called()


def test_selected_key_reaches_model_port_but_not_saved_or_presented_data(consumer):
    presets = (
        VisionPreset("unused", "https://unused.example/v1", "unused-model", "synthetic-unused-key"),
        VisionPreset("selected", "https://selected.example/v1", "selected-model", "synthetic-selected-key"),
    )
    boundary, request, facts, model, store, output, _ = consumer(presets)

    assert boundary.execute(request) is None

    expected = VisionPreset(
        "selected", "https://selected.example/v1", "selected-model", "synthetic-selected-key",
    )
    if isinstance(request, ExtractPdfTextRequest):
        facts.extract.assert_called_once_with(b"%PDF-credential-test")
        model.extract_page.assert_called_once_with(
            pdf=b"%PDF-credential-test", page_number=1, preset=expected,
        )
        supplied = model.extract_page.call_args.kwargs["preset"]
        assert store.save.call_args.kwargs == {"pdf": b"%PDF-credential-test"}
    else:
        facts.load_page.assert_called_once_with(document_id="document-92", page_number=1)
        model.propose.assert_called_once_with(
            raw_text="ทีC", spans=(SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),),
            preset=expected,
        )
        supplied = model.propose.call_args.kwargs["preset"]
    # Assert secret independently: preset equality must not conceal a wrong key.
    assert supplied.api_key == "synthetic-selected-key"
    store.save.assert_called_once()
    output.present.assert_called_once()
    for data in (store.save.call_args.args[0], output.present.call_args.args[0]):
        serialized = json.dumps(asdict(data), ensure_ascii=False)
        assert "api_key" not in serialized
        assert "synthetic-selected-key" not in serialized
        assert "synthetic-unused-key" not in serialized
    for key in ("synthetic-selected-key", "synthetic-unused-key"):
        assert key not in repr(presets)
        assert key not in repr(ModelPresetCatalogue(presets))
        assert key not in repr(ExtractionConfig(presets))


def test_renamed_v2_example_supplies_required_keys_for_both_consumers(consumer):
    # Example-file contract only; not a test of production CLI config loading.
    backend = Path(__file__).resolve().parents[5]
    data = json.loads((backend / "examples/document_processing_config.json").read_text())
    presets = tuple(VisionPreset(**entry) for entry in data["presets"])
    boundary, request, facts, model, store, output, _ = consumer(presets)
    request = replace(request, preset_name="local-offline")

    assert boundary.execute(request) is None

    assert facts.mock_calls
    supplied = (model.extract_page.call_args.kwargs["preset"]
                if isinstance(request, ExtractPdfTextRequest)
                else model.propose.call_args.kwargs["preset"])
    assert supplied.name == "local-offline"
    assert supplied.endpoint == "https://vision.example/v1"
    assert supplied.model == "not-configured"
    assert supplied.api_key == "REPLACE_WITH_YOUR_API_KEY"
    store.save.assert_called_once()
    output.present.assert_called_once()
