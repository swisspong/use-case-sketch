"""Agreed seam: real Input Boundary/Interactor/domain, mocked I/O ports.

Extraction only suggests OCR; it never invokes a model. OCR is a separate,
later use case that the user triggers explicitly.
"""

from unittest.mock import create_autospec

import pytest

from contexts.document_processing.v3.application.use_cases.extract_pdf_text.configuration import (
    ExtractionConfig,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.errors import (
    DocumentStorageError,
    InvalidExtractionConfiguration,
    InvalidPdfExtractionResult,
    InvalidStorageResult,
    PdfExtractionError,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.input_boundary import (
    ExtractPdfTextInputBoundary,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.interactor import (
    ExtractPdfTextInteractor,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.output_boundary import (
    ExtractPdfTextOutputBoundary,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.ports import (
    ExtractionStore,
    ParsedPdf,
    PdfRejected,
    PdfTextExtractor,
    SavedDocument,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.request import (
    ExtractPdfTextRequest,
)
from contexts.document_processing.v3.application.use_cases.extract_pdf_text.response import (
    ExtractedPage,
    ExtractionSaved,
    ExtractionRejected,
)
from contexts.document_processing.v3.domain.documents.extraction import (
    PageExtraction,
    SourcePage,
)
from contexts.document_processing.v3.domain.documents.text_quality import (
    RawPageQuality,
    SuspiciousTextSpan,
)


@pytest.fixture
def ports():
    parser = create_autospec(PdfTextExtractor, instance=True)
    store = create_autospec(ExtractionStore, instance=True)
    output = create_autospec(ExtractPdfTextOutputBoundary, instance=True)
    store.save.return_value = SavedDocument("document-82")
    return parser, store, output


def execute(ports, *, threshold=60.0, config=None, pdf=b"%PDF-upload-82"):
    parser, store, output = ports
    boundary: ExtractPdfTextInputBoundary = ExtractPdfTextInteractor(
        pdf_extractor=parser, store=store, output=output,
        config=config if config is not None else ExtractionConfig(threshold),
    )
    return boundary.execute(ExtractPdfTextRequest(pdf))


def detect(threshold=0):
    return ExtractionConfig(suspicious_threshold_percent=threshold)


# --- OCR suggestion -------------------------------------------------------


def test_page_with_problem_characters_above_threshold_is_suggested_for_ocr_unchanged(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC เชืMอ"), SourcePage(2, "ไทย")))

    assert execute(ports, threshold=20) is None

    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "ทีC เชืMอ", True, "problem_characters", 2, 8, 25.0),
        PageExtraction(2, "ไทย", False, None, 0, 3, 0.0),
    )
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "ทีC เชืMอ", True, "problem_characters", 2, 8, 25.0),
        ExtractedPage(2, "ไทย", False, None, 0, 3, 0.0),
    )))


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_blank_page_is_suggested_for_ocr_and_its_source_text_is_kept(ports, text):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, text),))

    execute(ports)

    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, text, True, "blank_page", 0, 0, 0.0),
    )
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, text, True, "blank_page", 0, 0, 0.0),
    )))


def test_replacement_and_font_signals_are_counted_together_once_per_position(ports):
    parser, store, output = ports
    # 1 x U+FFFD + 1 isolated Latin + 1 split syllable + 1 private use = 4 of 10.
    parser.extract.return_value = ParsedPdf((SourcePage(1, "\ufffdทีC ป่ วย\ue000ก"),))

    execute(ports, threshold=39.9)

    page, = store.save.call_args.args[0].pages
    assert (page.problem_character_count, page.non_whitespace_character_count) == (4, 10)
    assert page.problem_percent == 40.0
    assert (page.ocr_suggested, page.ocr_reason) == (True, "problem_characters")


@pytest.mark.parametrize("threshold,text", [
    (60, "\ufffd \ufffd\n\ufffdab"),  # exactly 3/5 = 60%; whitespace excluded
    (40, "\ufffd\ufffdabc"),          # injected threshold, not hardcoded 60
    (25, "ทีC เชืMอ"),                # font signals use the same strict comparison
    (0, "Readable"),
    (100, "\ufffd\ufffd"),
])
def test_problem_percentage_equal_to_threshold_is_not_suggested(ports, threshold, text):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, text),))

    execute(ports, threshold=threshold)

    page, = store.save.call_args.args[0].pages
    assert (page.text, page.ocr_suggested, page.ocr_reason) == (text, False, None)
    assert output.present.call_args.args[0].pages[0].ocr_suggested is False


def test_omitting_server_threshold_uses_sixty_percent(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "\ufffd\ufffd\ufffdab"), SourcePage(2, "\ufffd\ufffd\ufffd\ufffda"),
    ))

    execute(ports, config=ExtractionConfig())

    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "\ufffd\ufffd\ufffdab", False, None, 3, 5, 60.0),
        PageExtraction(2, "\ufffd\ufffd\ufffd\ufffda", True, "problem_characters", 4, 5, 80.0),
    )


def test_suggestion_is_independent_of_the_optional_suspicious_report(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC เชืMอ"),))

    execute(ports, config=ExtractionConfig(1, suspicious_threshold_percent=None))

    document = store.save.call_args.args[0]
    assert document.raw_text_quality == ()
    assert document.pages == (PageExtraction(1, "ทีC เชืMอ", True, "problem_characters", 2, 8, 25.0),)


# --- Report-only suspicious-text projection ---------------------------------


def test_isolated_latin_signals_flag_raw_text_without_rewriting(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC เชืMอ"),))
    expected = RawPageQuality(
        number=1, raw_text="ทีC เชืMอ",
        spans=(
            SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),
            SuspiciousTextSpan(7, 8, "latin_adjacent_to_thai"),
        ),
        suspicious_character_count=2, non_whitespace_character_count=8,
        suspicious_percent=25.0, threshold_percent=0, flagged=True,
    )

    assert execute(ports, config=detect()) is None

    document = store.save.call_args.args[0]
    assert document.raw_text_quality == (expected,)
    assert document.pages == (PageExtraction(1, "ทีC เชืMอ", False, None, 2, 8, 25.0),)
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82", (ExtractedPage(1, "ทีC เชืMอ", False, None, 2, 8, 25.0),),
        raw_text_quality=(expected,),
    ))


@pytest.mark.parametrize("raw_text", ["ไทยCOVID-19", "วิตามินB12", "Englishไทย", "ไทยABไทย"])
def test_english_words_and_codes_are_not_isolated_latin_signals(ports, raw_text):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=detect())

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == ()
    assert report.suspicious_character_count == 0
    assert report.suspicious_percent == 0.0
    assert report.flagged is False
    assert report.raw_text == raw_text
    assert output.present.call_args.args[0].raw_text_quality == (report,)


@pytest.mark.parametrize("raw_text,position,character_count", [
    (" ่ก", 1, 2), ("ผู้ป ่ วย", 5, 7),
])
def test_thai_marks_without_a_base_are_reported_without_text_changes(ports, raw_text, position, character_count):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=detect())

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (SuspiciousTextSpan(position, position + 1, "thai_mark_sequence"),)
    assert report.suspicious_character_count == 1
    assert report.non_whitespace_character_count == character_count
    assert report.flagged is True
    assert report.raw_text == raw_text
    assert output.present.call_args.args[0].pages[0].text == raw_text


@pytest.mark.parametrize("raw_text", ["ก่้", "ก่่", "กิิ"])
def test_conflicting_or_repeated_thai_marks_report_only_the_marks(ports, raw_text):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=detect())

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


def test_replacement_controls_and_private_use_characters_are_reported_as_code_points(ports):
    parser, store, output = ports
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

    execute(ports, config=detect())

    assert store.save.call_args.args[0].raw_text_quality == (expected,)
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82",
        (ExtractedPage(1, "a\ufffd\x01\ue000\U000f0000", True, "problem_characters", 4, 5, 80.0),),
        raw_text_quality=(expected,),
    ))


@pytest.mark.parametrize("suspicious_threshold", [
    -1, 101, float("nan"), float("inf"), True, "0",
    pytest.param(10**1000, id="oversized-integer"),
])
def test_invalid_suspicious_threshold_cannot_save_or_present_a_report(ports, suspicious_threshold):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC"),))

    with pytest.raises(InvalidExtractionConfiguration):
        execute(ports, config=detect(suspicious_threshold))

    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("threshold,flagged", [(0, True), (24.9, True), (25, False), (25.1, False), (100, False)])
def test_suspicious_percentage_must_strictly_exceed_its_own_threshold(ports, threshold, flagged):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC เชืMอ"),))

    execute(ports, config=detect(threshold))

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.suspicious_percent == 25.0
    assert report.threshold_percent == threshold
    assert report.flagged is flagged
    assert output.present.call_args.args[0].raw_text_quality == (report,)


def test_non_ascii_latin_letters_are_also_detected_next_to_thai(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีÇ"),))

    execute(ports, config=detect())

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),)
    assert report.suspicious_character_count == 1
    assert report.non_whitespace_character_count == 3
    assert report.flagged is True
    assert output.present.call_args.args[0].pages[0].text == "ทีÇ"


@pytest.mark.parametrize("raw_text", ["C฿", "C๑", "C๏"])
def test_thai_currency_digits_and_punctuation_do_not_act_as_thai_letters(ports, raw_text):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=detect())

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == ()
    assert report.flagged is False
    assert output.present.call_args.args[0].pages[0].text == raw_text


@pytest.mark.parametrize("raw_text", [
    "ผู้ป่วย สิทธิ์ กิ๊บ ปุ๋ย", "ภาษาไทย\nCOVID-19\tB12\r\n",
    "ได้ เนื้อ", "แก่ บ้าน", "ที่ เป็น", "แพทย์ กรม", "กรณี HI", "สิบปี ", "แต่ 30",
])
def test_valid_thai_marks_and_normal_whitespace_are_not_reported(ports, raw_text):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=detect())

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == ()
    assert report.suspicious_percent == 0.0
    assert report.flagged is False
    assert output.present.call_args.args[0].pages[0].text == raw_text


@pytest.mark.parametrize("raw_text,start,end,character_count", [
    ("เปิ ดเผย", 2, 4, 7),     # เ-ิ needs a final consonant
    ("ผู้ป่ วย", 4, 6, 7),    # consonant + tone without vowel, then a space
    ("ฝ่ าย", 1, 3, 4),
    ("เปลี่ ยน", 4, 6, 7),
])
def test_space_inserted_inside_a_thai_syllable_is_reported(ports, raw_text, start, end, character_count):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, raw_text),))

    execute(ports, config=detect())

    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.spans == (SuspiciousTextSpan(start, end, "split_thai_syllable"),)
    assert report.suspicious_character_count == 1
    assert report.non_whitespace_character_count == character_count
    assert report.flagged is True
    assert output.present.call_args.args[0].pages[0].text == raw_text


def test_marks_detected_by_multiple_checks_are_counted_once(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "่่"),))

    execute(ports, config=detect(100))

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


def test_ordered_raw_reports_including_blank_source_are_saved_before_presentation(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "ทีC เชืMอ"), SourcePage(2, "ok"), SourcePage(3, " \n\t"),
    ))
    expected_reports = (
        RawPageQuality(1, "ทีC เชืMอ", (
            SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),
            SuspiciousTextSpan(7, 8, "latin_adjacent_to_thai"),
        ), 2, 8, 25.0, 0, True),
        RawPageQuality(2, "ok", (), 0, 2, 0.0, 0, False),
        RawPageQuality(3, " \n\t", (), 0, 0, 0.0, 0, False),
    )
    expected_pages = (
        PageExtraction(1, "ทีC เชืMอ", False, None, 2, 8, 25.0),
        PageExtraction(2, "ok", False, None, 0, 2, 0.0),
        PageExtraction(3, " \n\t", True, "blank_page", 0, 0, 0.0),
    )

    def acknowledge(document, *, pdf):
        assert pdf == b"%PDF-upload-82"
        assert document.raw_text_quality == expected_reports
        assert document.pages == expected_pages
        output.present.assert_not_called()
        return SavedDocument("document-82")

    store.save.side_effect = acknowledge

    assert execute(ports, config=detect()) is None

    store.save.assert_called_once()
    output.present.assert_called_once_with(ExtractionSaved(
        "document-82", (
            ExtractedPage(1, "ทีC เชืMอ", False, None, 2, 8, 25.0),
            ExtractedPage(2, "ok", False, None, 0, 2, 0.0),
            ExtractedPage(3, " \n\t", True, "blank_page", 0, 0, 0.0),
        ), raw_text_quality=expected_reports,
    ))


def test_report_storage_failure_never_emits_success_or_retries(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "ทีC"),))
    failure = DocumentStorageError("acknowledgement failed")
    store.save.side_effect = failure

    with pytest.raises(DocumentStorageError) as caught:
        execute(ports, config=detect())

    assert caught.value is failure
    store.save.assert_called_once()
    report = store.save.call_args.args[0].raw_text_quality[0]
    assert report.raw_text == "ทีC"
    assert report.spans == (SuspiciousTextSpan(2, 3, "latin_adjacent_to_thai"),)
    assert report.flagged is True
    output.present.assert_not_called()


# --- Workflow, rejection and system failures ------------------------------


def test_readable_pages_are_saved_in_order_before_one_success_outcome(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((
        SourcePage(1, "หน้าแรก\nHello"), SourcePage(2, "Second page"),
    ))

    def acknowledge(document, *, pdf):
        assert pdf == b"%PDF-upload-82"
        assert document.pages == (
            PageExtraction(1, "หน้าแรก\nHello", False, None, 0, 12, 0.0),
            PageExtraction(2, "Second page", False, None, 0, 10, 0.0),
        )
        output.present.assert_not_called()
        return SavedDocument("document-82")

    store.save.side_effect = acknowledge

    assert execute(ports) is None

    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    store.save.assert_called_once()
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "หน้าแรก\nHello", False, None, 0, 12, 0.0),
        ExtractedPage(2, "Second page", False, None, 0, 10, 0.0),
    )))


@pytest.mark.parametrize("code", ["invalid_pdf", "encrypted_pdf"])
def test_expected_pdf_rejection_is_presented_without_storage(ports, code):
    parser, store, output = ports
    parser.extract.return_value = PdfRejected(code)

    assert execute(ports) is None

    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    store.save.assert_not_called()
    output.present.assert_called_once_with(ExtractionRejected(code))


@pytest.mark.parametrize("pdf", [b"", None, "not bytes", bytearray(b"mutable PDF")])
def test_empty_or_non_bytes_upload_is_rejected_without_any_io(ports, pdf):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    assert execute(ports, pdf=pdf) is None

    parser.extract.assert_not_called()
    store.save.assert_not_called()
    output.present.assert_called_once_with(ExtractionRejected("invalid_pdf"))


@pytest.mark.parametrize("pages", [
    (), (SourcePage(0, "Readable"),), (SourcePage(True, "Readable"),),
    (SourcePage(2, "Readable"),), (SourcePage(1, None),),
    (SourcePage(1, "First"), SourcePage(1, "Duplicate")),
])
def test_malformed_parser_facts_cannot_be_saved_as_a_document(ports, pages):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf(pages)

    with pytest.raises(InvalidPdfExtractionResult):
        execute(ports)

    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("threshold", [
    -1, 101, float("nan"), float("inf"), True, "60",
    pytest.param(10**1000, id="oversized-integer"),
])
def test_invalid_trusted_threshold_cannot_produce_saved_state(ports, threshold):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))

    with pytest.raises(InvalidExtractionConfiguration):
        execute(ports, threshold=threshold)

    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("result", [None, {"pages": []}, PdfRejected("provider_down")])
def test_undeclared_parser_result_is_not_mapped_to_a_business_rejection(ports, result):
    parser, store, output = ports
    parser.extract.return_value = result

    with pytest.raises(InvalidPdfExtractionResult):
        execute(ports)

    store.save.assert_not_called()
    output.present.assert_not_called()


def test_presentation_failure_does_not_repeat_committed_storage_or_extraction(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    failure = RuntimeError("Presenter failed")
    output.present.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        execute(ports)

    assert caught.value is failure
    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    store.save.assert_called_once()
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    output.present.assert_called_once_with(ExtractionSaved("document-82", (
        ExtractedPage(1, "Readable", False, None, 0, 8, 0.0),
    )))


def test_parser_system_failure_propagates_without_downstream_effects(ports):
    parser, store, output = ports
    failure = PdfExtractionError("parser unavailable")
    parser.extract.side_effect = failure

    with pytest.raises(PdfExtractionError) as caught:
        execute(ports)

    assert caught.value is failure
    parser.extract.assert_called_once_with(b"%PDF-upload-82")
    store.save.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("acknowledgement", [None, "document-82", SavedDocument(""), SavedDocument(" "), SavedDocument(True)])
def test_invalid_storage_acknowledgement_cannot_emit_success(ports, acknowledgement):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    store.save.return_value = acknowledgement

    with pytest.raises(InvalidStorageResult):
        execute(ports)

    store.save.assert_called_once()
    assert store.save.call_args.kwargs == {"pdf": b"%PDF-upload-82"}
    output.present.assert_not_called()


def test_storage_failure_propagates_without_false_success_or_retry(ports):
    parser, store, output = ports
    parser.extract.return_value = ParsedPdf((SourcePage(1, "Readable"),))
    failure = DocumentStorageError("commit acknowledgement failed")
    store.save.side_effect = failure

    with pytest.raises(DocumentStorageError) as caught:
        execute(ports)

    assert caught.value is failure
    assert store.save.call_args.args[0].pages == (
        PageExtraction(1, "Readable", False, None, 0, 8, 0.0),
    )
    store.save.assert_called_once()
    output.present.assert_not_called()
