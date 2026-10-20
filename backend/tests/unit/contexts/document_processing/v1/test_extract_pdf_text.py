"""Agreed seam: real Input Boundary/Interactor/domain, mocked I/O ports."""

from unittest.mock import create_autospec

import pytest

from contexts.document_processing.v1.application.use_cases.extract_pdf_text.configuration import (
    ExtractionConfig,
    VisionPreset,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.errors import (
    DocumentStorageError,
    FallbackExtractionError,
    InvalidExtractionConfiguration,
    InvalidFallbackExtractionResult,
    InvalidPdfExtractionResult,
    InvalidStorageResult,
    PdfExtractionError,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.input_boundary import (
    ExtractPdfTextInputBoundary,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.interactor import (
    ExtractPdfTextInteractor,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.output_boundary import (
    ExtractPdfTextOutputBoundary,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.ports import (
    ExtractionStore,
    FallbackExtractor,
    ParsedPdf,
    PdfRejected,
    PdfTextExtractor,
    SavedDocument,
    VisionText,
    VisionUnreadable,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.request import (
    ExtractPdfTextRequest,
)
from contexts.document_processing.v1.application.use_cases.extract_pdf_text.response import (
    ExtractedPage,
    ExtractionSaved,
    ExtractionRejected,
)
from contexts.document_processing.v1.domain.documents.extraction import (
    PageExtraction,
    SourcePage,
)


@pytest.fixture
def ports():
    parser = create_autospec(PdfTextExtractor, instance=True)
    fallback = create_autospec(FallbackExtractor, instance=True)
    store = create_autospec(ExtractionStore, instance=True)
    output = create_autospec(ExtractPdfTextOutputBoundary, instance=True)
    preset = VisionPreset("approved-vision", "https://vision.example/v1", "vision-model")
    store.save.return_value = SavedDocument("document-82")
    return parser, fallback, store, output, preset


def execute(ports, *, threshold=60.0, preset_name="approved-vision", config=None, pdf=b"%PDF-upload-82"):
    parser, fallback, store, output, preset = ports
    boundary: ExtractPdfTextInputBoundary = ExtractPdfTextInteractor(
        pdf_extractor=parser, fallback=fallback, store=store, output=output,
        config=config if config is not None else ExtractionConfig((preset,), threshold),
    )
    return boundary.execute(ExtractPdfTextRequest(pdf, preset_name))


def test_readable_pages_are_saved_in_order_before_one_success_outcome(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "หน้าแรก\nHello"), SourcePage(2, "Second page"),
    ))
    expected_pages = (
        ExtractedPage(1, "หน้าแรก\nHello", "extracted", "pdf_text"),
        ExtractedPage(2, "Second page", "extracted", "pdf_text"),
    )

    def acknowledge(document, *, pdf):
        assert pdf == b"%PDF-upload-82"
        assert document.pages == (
            PageExtraction(1, "หน้าแรก\nHello", "extracted", "pdf_text"),
            PageExtraction(2, "Second page", "extracted", "pdf_text"),
        )
        output.present.assert_not_called()
        return SavedDocument("document-82")

    store.save.side_effect = acknowledge

    assert execute(ports) is None

    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    fallback.extract_page.assert_not_called()
    store.save.assert_called_once()
    output.present.assert_called_once_with(ExtractionSaved("document-82", expected_pages))


def test_original_pdf_is_supplied_with_the_page_results_for_atomic_storage(ports):
    parser, _, store, _, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    execute(ports)

    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "Readable", "extracted", "pdf_text"),
    )


def test_only_the_low_quality_page_uses_vision_and_saves_model_provenance(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "First"), SourcePage(2, "\ufffd\ufffd\ufffd\ufffda"),
        SourcePage(3, "Third"),
    ))
    fallback.extract_page.return_value = VisionText("Recovered second page")

    execute(ports)

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=2,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "First", "extracted", "pdf_text"),
        PageExtraction(2, "Recovered second page", "extracted", "vision",
                       preset_name="approved-vision", model="vision-model"),
        PageExtraction(3, "Third", "extracted", "pdf_text"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "First", "extracted", "pdf_text"),
        ExtractedPage(2, "Recovered second page", "extracted", "vision",
                      preset_name="approved-vision", model="vision-model"),
        ExtractedPage(3, "Third", "extracted", "pdf_text"),
    )))


@pytest.mark.parametrize("vision_text", ["", " \n\t", "\ufffd\ufffd\ufffd\ufffda"])
def test_unreadable_vision_text_is_failed_without_retry_or_retaining_bad_text(ports, vision_text):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "\ufffd\ufffd\ufffd\ufffda"),))
    fallback.extract_page.return_value = VisionText(vision_text)

    execute(ports)

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, None, "failed", "vision", "unreadable", "approved-vision", "vision-model"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, None, "failed", "vision", "unreadable", "approved-vision", "vision-model"),
    )))


def test_provider_failure_saves_partial_results_and_continues_later_pages(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "First"), SourcePage(2, "\ufffd\ufffd\ufffd\ufffda"), SourcePage(3, ""),
    ))

    def read_page(*, pdf, page_number, preset):
        assert pdf == b"%PDF-upload-82"
        assert preset == VisionPreset("approved-vision", "https://vision.example/v1", "vision-model")
        if page_number == 2:
            raise FallbackExtractionError("private provider details")
        assert page_number == 3
        return VisionText("Recovered third page")

    fallback.extract_page.side_effect = read_page

    execute(ports)

    assert [call.kwargs["page_number"] for call in fallback.extract_page.call_args_list] == [2, 3]
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "First", "extracted", "pdf_text"),
        PageExtraction(2, None, "failed", "vision", "fallback_unavailable", "approved-vision", "vision-model"),
        PageExtraction(3, "Recovered third page", "extracted", "vision", None, "approved-vision", "vision-model"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "First", "extracted", "pdf_text"),
        ExtractedPage(2, None, "failed", "vision", "fallback_unavailable", "approved-vision", "vision-model"),
        ExtractedPage(3, "Recovered third page", "extracted", "vision", None, "approved-vision", "vision-model"),
    )))


def test_model_inability_is_a_saved_failed_page_not_a_system_exception(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, ""),))
    fallback.extract_page.return_value = VisionUnreadable()

    execute(ports)

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, None, "failed", "vision", "unreadable", "approved-vision", "vision-model"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, None, "failed", "vision", "unreadable", "approved-vision", "vision-model"),
    )))


@pytest.mark.parametrize("code", ["invalid_pdf", "encrypted_pdf"])
def test_expected_pdf_rejection_is_presented_without_fallback_or_storage(ports, code):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = PdfRejected(code)

    assert execute(ports) is None

    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_called_once_with(ExtractionRejected(code))


@pytest.mark.parametrize("name", ["unapproved-model", "https://evil.example/v1", "", None, "APPROVED-VISION", " approved-vision "])
def test_unknown_upload_preset_is_rejected_before_any_io(ports, name):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    assert execute(ports, preset_name=name) is None

    parser.extract.assert_not_called()
    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_called_once_with(ExtractionRejected("invalid_preset"))


@pytest.mark.parametrize("presets", [
    (), (object(),),
    (VisionPreset("", "https://vision.example/v1", "vision-model"),),
    (VisionPreset("approved-vision", "", "vision-model"),),
    (VisionPreset("approved-vision", "https://vision.example/v1", " "),),
    (VisionPreset("duplicate", "https://first.example/v1", "first-model"),
     VisionPreset("duplicate", "https://second.example/v1", "second-model")),
])
def test_invalid_admin_catalogue_is_a_system_error_before_any_io(ports, presets):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    with pytest.raises(InvalidExtractionConfiguration):
        execute(ports, config=ExtractionConfig(presets))

    parser.extract.assert_not_called()
    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("pdf", [b"", None, "not bytes", bytearray(b"mutable PDF")])
def test_empty_or_non_bytes_upload_is_rejected_without_any_io(ports, pdf):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    assert execute(ports, pdf=pdf) is None

    parser.extract.assert_not_called()
    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_called_once_with(ExtractionRejected("invalid_pdf"))


@pytest.mark.parametrize("endpoint", [
    "not-a-url", "ftp://vision.example/v1", "https:///v1",
    "https://user:secret@vision.example/v1", "https://[broken/v1",
])
def test_invalid_trusted_endpoint_is_not_treated_as_a_provider_outage(ports, endpoint):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    config = ExtractionConfig((VisionPreset("approved-vision", endpoint, "vision-model"),))

    with pytest.raises(InvalidExtractionConfiguration):
        execute(ports, config=config)

    parser.extract.assert_not_called()
    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("pages", [
    (), (SourcePage(0, "Readable"),), (SourcePage(True, "Readable"),),
    (SourcePage(2, "Readable"),), (SourcePage(1, None),),
    (SourcePage(1, "First"), SourcePage(1, "Duplicate")),
])
def test_malformed_parser_facts_cannot_be_saved_as_a_document(ports, pages):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf(pages)

    with pytest.raises(InvalidPdfExtractionResult):
        execute(ports)

    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("threshold", [
    -1, 101, float("nan"), float("inf"), True, "60",
    pytest.param(10**1000, id="oversized-integer"),
])
def test_invalid_trusted_threshold_cannot_produce_saved_state(ports, threshold):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    with pytest.raises(InvalidExtractionConfiguration):
        execute(ports, threshold=threshold)

    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


# Tests of already-present logic: no artificial red is manufactured here.
def test_omitting_server_threshold_uses_sixty_percent(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "\ufffd\ufffd\ufffdab"),))

    execute(ports, config=ExtractionConfig((preset,)))

    fallback.extract_page.assert_not_called()
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "\ufffd\ufffd\ufffdab", "extracted", "pdf_text"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "\ufffd\ufffd\ufffdab", "extracted", "pdf_text"),
    )))


def test_selection_uses_the_second_approved_endpoint_and_model_and_records_them(ports):
    parser, fallback, store, output, first = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, ""),))
    fallback.extract_page.return_value = VisionText("Recovered with selected model")
    second = VisionPreset("vision-large", "https://other-vision.example/v1", "other-model")

    execute(ports, preset_name="vision-large", config=ExtractionConfig((first, second)))

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("vision-large", "https://other-vision.example/v1", "other-model"),
    )
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "Recovered with selected model", "extracted", "vision", None, "vision-large", "other-model"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "Recovered with selected model", "extracted", "vision", None, "vision-large", "other-model"),
    )))


@pytest.mark.parametrize("source_text,threshold,vision_text", [
    ("", 60, "\ufffd \ufffd\n\ufffdab"),
    (" \n\t", 40, "\ufffd\ufffdabc"),
    ("", 100, "\ufffd\ufffd"),
])
def test_empty_source_falls_back_and_vision_uses_the_same_injected_threshold(ports, source_text, threshold, vision_text):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, source_text),))
    fallback.extract_page.return_value = VisionText(vision_text)

    execute(ports, threshold=threshold)

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, vision_text, "extracted", "vision", None, "approved-vision", "vision-model"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, vision_text, "extracted", "vision", None, "approved-vision", "vision-model"),
    )))


@pytest.mark.parametrize("result", [None, {"pages": []}, PdfRejected("provider_down")])
def test_undeclared_parser_result_is_not_mapped_to_a_business_rejection(ports, result):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = result

    with pytest.raises(InvalidPdfExtractionResult):
        execute(ports)

    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("result", [None, {"text": "untrusted"}, VisionText(None), VisionText(4)])
def test_malformed_fallback_facts_do_not_become_failed_pages_or_success(ports, result):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, ""),))
    fallback.extract_page.return_value = result

    with pytest.raises(InvalidFallbackExtractionResult):
        execute(ports)

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    store.save.assert_not_called()
    output.present.assert_not_called()


def test_unexpected_fallback_error_propagates_and_stops_later_pages(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, ""), SourcePage(2, "")))
    failure = RuntimeError("unexpected bug")
    fallback.extract_page.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        execute(ports)

    assert caught.value is failure
    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    store.save.assert_not_called()
    output.present.assert_not_called()


def test_presentation_failure_does_not_repeat_committed_storage_or_extraction(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    failure = RuntimeError("Presenter failed")
    output.present.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        execute(ports)

    assert caught.value is failure
    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    store.save.assert_called_once()
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    fallback.extract_page.assert_not_called()
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "Readable", "extracted", "pdf_text"),
    )))


@pytest.mark.parametrize("threshold,text", [
    (60, "\ufffd \ufffd\n\ufffdab"),  # exactly 3/5 = 60%; whitespace excluded
    (40, "\ufffd\ufffdabc"),          # injected threshold, not hardcoded 60
    (0, "Readable"),
    (100, "\ufffd\ufffd"),
])
def test_quality_equal_to_threshold_does_not_fall_back(ports, threshold, text):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, text),))

    execute(ports, threshold=threshold)

    fallback.extract_page.assert_not_called()
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, text, "extracted", "pdf_text"),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, text, "extracted", "pdf_text"),
    )))


def test_parser_system_failure_propagates_without_downstream_effects(ports):
    parser, fallback, store, output, _ = ports
    failure = PdfExtractionError("parser unavailable")
    parser.extract.side_effect = failure

    with pytest.raises(PdfExtractionError) as caught:
        execute(ports)

    assert caught.value is failure
    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("acknowledgement", [None, "document-82", SavedDocument(""), SavedDocument(" "), SavedDocument(True)])
def test_invalid_storage_acknowledgement_cannot_emit_success(ports, acknowledgement):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    store.save.return_value = acknowledgement

    with pytest.raises(InvalidStorageResult):
        execute(ports)

    store.save.assert_called_once()
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    fallback.extract_page.assert_not_called()
    output.present.assert_not_called()


def test_storage_failure_propagates_without_false_success_or_retry(ports):
    parser, fallback, store, output, _ = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    failure = DocumentStorageError("commit acknowledgement failed")
    store.save.side_effect = failure

    with pytest.raises(DocumentStorageError) as caught:
        execute(ports)

    assert caught.value is failure
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "Readable", "extracted", "pdf_text"),
    )
    store.save.assert_called_once()
    fallback.extract_page.assert_not_called()
    output.present.assert_not_called()
