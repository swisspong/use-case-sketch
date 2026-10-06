"""Agreed seam: real Input Boundary/Interactor/domain, mocked I/O ports."""

from unittest.mock import create_autospec

import pytest

from contexts.document_processing.v2.application.use_cases.extract_pdf_text.configuration import (
    ExtractionConfig,
    VisionPreset,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.errors import (
    DocumentStorageError,
    FallbackExtractionError,
    InvalidExtractionConfiguration,
    InvalidFallbackExtractionResult,
    InvalidPdfExtractionResult,
    InvalidStorageResult,
    PdfExtractionError,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.input_boundary import (
    ExtractPdfTextInputBoundary,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.interactor import (
    ExtractPdfTextInteractor,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.output_boundary import (
    ExtractPdfTextOutputBoundary,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.ports import (
    ExtractionStore,
    FallbackExtractor,
    ParsedPdf,
    PdfRejected,
    PdfTextExtractor,
    SavedDocument,
    VisionText,
    VisionUnreadable,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.request import (
    ExtractPdfTextRequest,
)
from contexts.document_processing.v2.application.use_cases.extract_pdf_text.response import (
    ExtractedPage,
    ExtractionSaved,
    ExtractionRejected,
)
from contexts.document_processing.v2.domain.documents.extraction import (
    PageExtraction,
    SourcePage,
)
from contexts.document_processing.v2.domain.documents.text_quality import (
    RawPageQuality,
    SuspiciousTextSpan,
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


def test_isolated_latin_signals_flag_raw_text_without_fallback_or_rewriting(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC เชืMอ"),))
    config = ExtractionConfig((preset,), suspicious_threshold_percent=0)
    expected = RawPageQuality(
        number=1, raw_text="ทีC เชืMอ",
        spans=(
            SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),
            SuspiciousTextSpan(7, 8, "latin_adjacent_to_thai"),
        ),
        suspicious_character_count=2, non_whitespace_character_count=8,
        suspicious_percent=25.0, threshold_percent=0, flagged=True,
    )

    assert execute(ports, config=config) is None

    document = store.save.call_args.args[0]
    assert document.raw_text_quality == (expected,)
    assert document.pages == (PageExtraction(1, "ทีC เชืMอ", "extracted", "pdf_text"),)
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    fallback.extract_page.assert_not_called()
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82", (ExtractedPage(1, "ทีC เชืMอ", "extracted", "pdf_text"),),
        raw_text_quality=(expected,),
    ))


@pytest.mark.parametrize("raw_text", ["ไทยCOVID-19", "วิตามินB12", "Englishไทย", "ไทยABไทย"])
def test_english_words_and_codes_are_not_isolated_latin_signals(ports, raw_text):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == ()
    assert report.suspicious_character_count == 0
    assert report.suspicious_percent == 0.0
    assert report.flagged is False
    assert report.raw_text == raw_text
    assert output.present.call_args.args[0].raw_text_quality == (report,)
    fallback.extract_page.assert_not_called()


@pytest.mark.parametrize("raw_text,position,character_count", [
    (" ่ก", 1, 2), ("ผู้ป ่ วย", 5, 7),
])
def test_thai_marks_without_a_base_are_reported_without_text_changes(ports, raw_text, position, character_count):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (SuspiciousTextSpan(position, position + 1, "thai_mark_sequence"),)
    assert report.suspicious_character_count == 1
    assert report.non_whitespace_character_count == character_count
    assert report.flagged is True
    assert report.raw_text == raw_text
    assert output.present.call_args.args[0].pages[0].text == raw_text
    fallback.extract_page.assert_not_called()


@pytest.mark.parametrize("raw_text", ["ก่้", "ก่่", "กิิ"])
def test_conflicting_or_repeated_thai_marks_report_only_the_marks(ports, raw_text):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (
        SuspiciousTextSpan(1, 2, "thai_mark_sequence"),
        SuspiciousTextSpan(2, 3, "thai_mark_sequence"),
    )
    assert report.suspicious_character_count == 2
    assert report.non_whitespace_character_count == 3
    assert report.suspicious_percent == pytest.approx(66.6666666667)
    assert report.flagged is True
    assert output.present.call_args.args[0].pages[0].text == raw_text
    fallback.extract_page.assert_not_called()


def test_replacement_controls_and_private_use_characters_are_reported_as_code_points(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "a\ufffd\x01\ue000\U000f0000"),))
    expected = RawPageQuality(
        number=1, raw_text="a\ufffd\x01\ue000\U000f0000",
        spans=(
            SuspiciousTextSpan(1, 2, "replacement_character"),
            SuspiciousTextSpan(2, 3, "unexpected_control"),
            SuspiciousTextSpan(3, 4, "private_use_character"),
            SuspiciousTextSpan(4, 5, "private_use_character"),
        ),
        suspicious_character_count=4, non_whitespace_character_count=5,
        suspicious_percent=80.0, threshold_percent=0, flagged=True,
    )

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    assert store.save.call_args.args[0].raw_text_quality == (expected,)
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82", (ExtractedPage(1, "a\ufffd\x01\ue000\U000f0000", "extracted", "pdf_text"),),
        raw_text_quality=(expected,),
    ))
    fallback.extract_page.assert_not_called()


@pytest.mark.parametrize("suspicious_threshold", [
    -1, 101, float("nan"), float("inf"), True, "0",
    pytest.param(10**1000, id="oversized-integer"),
])
def test_invalid_suspicious_threshold_cannot_save_or_present_a_report(ports, suspicious_threshold):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC"),))
    config = ExtractionConfig((preset,), suspicious_threshold_percent=suspicious_threshold)

    with pytest.raises(InvalidExtractionConfiguration):
        execute(ports, config=config)

    fallback.extract_page.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_not_called()


# Coverage of already-implemented strict comparison; no artificial red.
@pytest.mark.parametrize("threshold,flagged", [(0, True), (24.9, True), (25, False), (25.1, False), (100, False)])
def test_suspicious_percentage_must_strictly_exceed_its_own_threshold(ports, threshold, flagged):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC เชืMอ"),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=threshold))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.suspicious_percent == 25.0
    assert report.threshold_percent == threshold
    assert report.flagged is flagged
    assert output.present.call_args.args[0].raw_text_quality == (report,)
    fallback.extract_page.assert_not_called()


@pytest.mark.parametrize("fallback_result,final_text,status,failure_code", [
    (VisionText("ทีC"), "ทีC", "extracted", None),
    (VisionText("\ufffd"), None, "failed", "unreadable"),
    (VisionUnreadable(), None, "failed", "unreadable"),
    (FallbackExtractionError("private details"), None, "failed", "fallback_unavailable"),
])
def test_fallback_preserves_raw_assessment_without_assessing_its_own_text(ports, fallback_result, final_text, status, failure_code):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "\ufffd"),))
    if isinstance(fallback_result, FallbackExtractionError):
        fallback.extract_page.side_effect = fallback_result
    else:
        fallback.extract_page.return_value = fallback_result
    expected = RawPageQuality(
        number=1, raw_text="\ufffd",
        spans=(SuspiciousTextSpan(0, 1, "replacement_character"),),
        suspicious_character_count=1, non_whitespace_character_count=1,
        suspicious_percent=100.0, threshold_percent=0, flagged=True,
    )

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    assert store.save.call_args.args[0].raw_text_quality == (expected,)
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, final_text, status, "vision", failure_code, "approved-vision", "vision-model"),
    )
    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=1,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82",
        (ExtractedPage(1, final_text, status, "vision", failure_code, "approved-vision", "vision-model"),),
        raw_text_quality=(expected,),
    ))


def test_non_ascii_latin_letters_are_also_detected_next_to_thai(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีÇ"),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),)
    assert report.suspicious_character_count == 1
    assert report.non_whitespace_character_count == 3
    assert report.flagged is True
    assert output.present.call_args.args[0].pages[0].text == "ทีÇ"
    fallback.extract_page.assert_not_called()


@pytest.mark.parametrize("raw_text", ["C฿", "C๑", "C๏"])
def test_thai_currency_digits_and_punctuation_do_not_act_as_thai_letters(ports, raw_text):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == ()
    assert report.flagged is False
    assert output.present.call_args.args[0].pages[0].text == raw_text
    fallback.extract_page.assert_not_called()


@pytest.mark.parametrize("raw_text", [
    "ผู้ป่วย สิทธิ์ กิ๊บ ปุ๋ย", "ภาษาไทย\nCOVID-19\tB12\r\n", "เปิ ด",
])
def test_valid_thai_marks_and_normal_whitespace_are_not_reported(ports, raw_text):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == ()
    assert report.suspicious_percent == 0.0
    assert report.flagged is False
    assert output.present.call_args.args[0].pages[0].text == raw_text
    fallback.extract_page.assert_not_called()


def test_marks_detected_by_multiple_checks_are_counted_once(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "่่"),))

    execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=100))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (
        SuspiciousTextSpan(0, 1, "thai_mark_sequence"),
        SuspiciousTextSpan(1, 2, "thai_mark_sequence"),
    )
    assert report.suspicious_character_count == 2
    assert report.non_whitespace_character_count == 2
    assert report.suspicious_percent == 100.0
    assert report.flagged is False
    assert output.present.call_args.args[0].pages[0].text == "่่"
    fallback.extract_page.assert_not_called()


def test_ordered_raw_reports_including_blank_source_are_saved_before_presentation(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "ทีC เชืMอ"), SourcePage(2, "ok"), SourcePage(3, " \n\t"),
    ))
    fallback.extract_page.return_value = VisionText("ทีC")
    expected_reports = (
        RawPageQuality(1, "ทีC เชืMอ", (
            SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),
            SuspiciousTextSpan(7, 8, "latin_adjacent_to_thai"),
        ), 2, 8, 25.0, 0, True),
        RawPageQuality(2, "ok", (), 0, 2, 0.0, 0, False),
        RawPageQuality(3, " \n\t", (), 0, 0, 0.0, 0, False),
    )

    def acknowledge(document, *, pdf):
        assert pdf == b"%PDF-upload-82"
        assert document.raw_text_quality == expected_reports
        assert document.pages == (
            PageExtraction(1, "ทีC เชืMอ", "extracted", "pdf_text"),
            PageExtraction(2, "ok", "extracted", "pdf_text"),
            PageExtraction(3, "ทีC", "extracted", "vision", None, "approved-vision", "vision-model"),
        )
        output.present.assert_not_called()
        return SavedDocument("document-82")

    store.save.side_effect = acknowledge

    assert execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0)) is None

    fallback.extract_page.assert_called_once_with(
        pdf=b"%PDF-upload-82", page_number=3,
        preset=VisionPreset("approved-vision", "https://vision.example/v1", "vision-model"),
    )
    store.save.assert_called_once()
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82", (
            ExtractedPage(1, "ทีC เชืMอ", "extracted", "pdf_text"),
            ExtractedPage(2, "ok", "extracted", "pdf_text"),
            ExtractedPage(3, "ทีC", "extracted", "vision", None, "approved-vision", "vision-model"),
        ), raw_text_quality=expected_reports,
    ))


def test_report_storage_failure_never_emits_success_or_retries(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC"),))
    failure = DocumentStorageError("acknowledgement failed")
    store.save.side_effect = failure

    with pytest.raises(DocumentStorageError) as caught:
        execute(ports, config=ExtractionConfig((preset,), suspicious_threshold_percent=0))

    assert caught.value is failure
    store.save.assert_called_once()
    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.raw_text == "ทีC"
    assert report.spans == (SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),)
    assert report.flagged is True
    fallback.extract_page.assert_not_called()
    output.present.assert_not_called()


def test_existing_configuration_leaves_new_assessment_explicitly_absent(ports):
    parser, fallback, store, output, preset = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC"),))

    execute(ports, config=ExtractionConfig((preset,)))

    assert store.save.call_args.args[0].raw_text_quality == ()
    assert store.save.call_args.args[0].pages == (PageExtraction(1, "ทีC", "extracted", "pdf_text"),)
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82", (ExtractedPage(1, "ทีC", "extracted", "pdf_text"),),
    ))
    fallback.extract_page.assert_not_called()


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
