"""Agreed seam: real Input Boundary/Interactor/OcrAttempt, mocked I/O ports."""

from unittest.mock import create_autospec

import pytest

from contexts.document_processing.v3.application.model_presets import VisionPreset
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.configuration import OcrConfig
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.errors import (
    DocumentSourceError, InvalidOcrConfiguration, InvalidOcrResult, OcrAttemptStorageError,
    OcrProviderError, PageRenderingError,
)
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.input_boundary import (
    OcrDocumentPagesInputBoundary,
)
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.interactor import (
    OcrDocumentPagesInteractor,
)
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.output_boundary import (
    OcrDocumentPagesOutputBoundary,
)
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.ports import (
    DocumentNotFound, OcrAttemptStore, OcrReader, OcrText, OcrUnreadable, PageImage, PageRenderer, SavedDocumentForOcr,
    SavedDocumentSource, SavedOcrAttempt,
)
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.request import (
    OcrDocumentPagesRequest,
)
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.response import (
    OcrAttemptSaved, OcrPageResult, OcrRejected,
)
from contexts.document_processing.v3.domain.documents.ocr_attempt import OcrPage, SuggestedPage

PDF = b"%PDF-saved-document-17"
OTHER = VisionPreset("other", "https://other.example/v1", "other-model", "synthetic-other-key")
SELECTED = VisionPreset("gemini", "https://litellm.example/v1", "gemini-3.8-flash", "synthetic-selected-key")


def image(number):
    return PageImage("image/png", f"png-of-page-{number}".encode())


@pytest.fixture
def ports():
    documents = create_autospec(SavedDocumentSource, instance=True)
    renderer = create_autospec(PageRenderer, instance=True)
    ocr = create_autospec(OcrReader, instance=True)
    attempts = create_autospec(OcrAttemptStore, instance=True)
    output = create_autospec(OcrDocumentPagesOutputBoundary, instance=True)
    documents.load.return_value = SavedDocumentForOcr("document-17", PDF, (
        SuggestedPage(1, True), SuggestedPage(2, False), SuggestedPage(3, True),
    ), threshold_percent=1)
    renderer.render.side_effect = lambda *, pdf, page_number: image(page_number)
    attempts.append.return_value = SavedOcrAttempt("attempt-5")
    return documents, renderer, ocr, attempts, output


def execute(ports, *, pages=None, preset="gemini", document_id="document-17", presets=(OTHER, SELECTED)):
    documents, renderer, ocr, attempts, output = ports
    boundary: OcrDocumentPagesInputBoundary = OcrDocumentPagesInteractor(
        documents=documents, renderer=renderer, ocr=ocr, attempts=attempts, output=output,
        config=OcrConfig(presets),
    )
    return boundary.execute(OcrDocumentPagesRequest(document_id, preset, pages))


def test_suggested_pages_are_read_with_the_selected_preset_saved_then_presented(ports):
    documents, renderer, ocr, attempts, output = ports
    texts = {image(1): "หน้าแรกที่อ่านได้", image(3): "หน้าสามเพื่อผู้ป่วย"}
    ocr.read.side_effect = lambda *, image, preset: OcrText(texts[image])

    def acknowledge(attempt):
        output.present.assert_not_called()
        return SavedOcrAttempt("attempt-5")

    attempts.append.side_effect = acknowledge

    assert execute(ports) is None

    documents.load.assert_called_once_with("document-17")
    assert [call.kwargs for call in renderer.render.call_args_list] == [
        {"pdf": PDF, "page_number": 1}, {"pdf": PDF, "page_number": 3},
    ]
    assert [call.kwargs for call in ocr.read.call_args_list] == [
        {"image": image(1), "preset": SELECTED}, {"image": image(3), "preset": SELECTED},
    ]
    assert all(call.kwargs["preset"].api_key == "synthetic-selected-key" for call in ocr.read.call_args_list)
    attempt = attempts.append.call_args.args[0]
    assert (attempt.document_id, attempt.preset_name, attempt.model, attempt.threshold_percent) == (
        "document-17", "gemini", "gemini-3.8-flash", 1,
    )
    assert attempt.pages == (
        OcrPage(1, True, "extracted", "หน้าแรกที่อ่านได้", 0, 17, 0.0),
        OcrPage(3, True, "extracted", "หน้าสามเพื่อผู้ป่วย", 0, 19, 0.0),
    )
    output.present.assert_called_once_with(OcrAttemptSaved("document-17", "attempt-5", (
        OcrPageResult(1, True, "extracted", "หน้าแรกที่อ่านได้"),
        OcrPageResult(3, True, "extracted", "หน้าสามเพื่อผู้ป่วย"),
    )))


@pytest.mark.parametrize("saved_threshold,text,expected", [
    (1, "ทีC เชืMอ", OcrPage(1, True, "unreadable", None, 2, 8, 25.0)),
    (24.9, "ทีC เชืMอ", OcrPage(1, True, "unreadable", None, 2, 8, 25.0)),
    (25, "ทีC เชืMอ", OcrPage(1, True, "extracted", "ทีC เชืMอ", 2, 8, 25.0)),  # equal is accepted
    (100, " \n\t", OcrPage(1, True, "unreadable", None, 0, 0, 0.0)),            # blank never accepted
])
def test_ocr_text_must_pass_the_threshold_saved_with_the_document(ports, saved_threshold, text, expected):
    documents, renderer, ocr, attempts, output = ports
    documents.load.return_value = SavedDocumentForOcr(
        "document-17", PDF, (SuggestedPage(1, True),), threshold_percent=saved_threshold,
    )
    ocr.read.return_value = OcrText(text)

    execute(ports)

    attempt = attempts.append.call_args.args[0]
    assert attempt.threshold_percent == saved_threshold
    assert attempt.pages == (expected,)
    output.present.assert_called_once_with(OcrAttemptSaved("document-17", "attempt-5", (
        OcrPageResult(1, True, expected.status, expected.text),
    )))


def test_explicit_pages_are_read_exactly_including_an_unsuggested_page_in_document_order(ports):
    documents, renderer, ocr, attempts, output = ports
    ocr.read.side_effect = lambda *, image, preset: OcrText(f"อ่าน {image.data.decode()[-1]}")

    execute(ports, pages=(3, 2))

    assert [call.kwargs["page_number"] for call in renderer.render.call_args_list] == [2, 3]
    assert [(page.number, page.was_suggested, page.status, page.text)
            for page in attempts.append.call_args.args[0].pages] == [
        (2, False, "extracted", "อ่าน 2"), (3, True, "extracted", "อ่าน 3"),
    ]
    output.present.assert_called_once_with(OcrAttemptSaved("document-17", "attempt-5", (
        OcrPageResult(2, False, "extracted", "อ่าน 2"), OcrPageResult(3, True, "extracted", "อ่าน 3"),
    )))


def assert_no_ocr_effects(ports):
    _, renderer, ocr, attempts, _ = ports
    renderer.render.assert_not_called()
    ocr.read.assert_not_called()
    attempts.append.assert_not_called()


@pytest.mark.parametrize("pages,code", [
    ((), "no_pages_selected"),
    ((4,), "page_not_found"), ((0,), "page_not_found"), ((True,), "page_not_found"),
    (("1",), "page_not_found"), ((1, 4), "page_not_found"),
    ((1, 1), "duplicate_page"),
])
def test_invalid_explicit_selection_is_rejected_without_ocr_or_storage(ports, pages, code):
    *_, output = ports

    assert execute(ports, pages=pages) is None

    assert_no_ocr_effects(ports)
    output.present.assert_called_once_with(OcrRejected(code))


def test_default_selection_without_suggested_pages_is_rejected(ports):
    documents, *_, output = ports
    documents.load.return_value = SavedDocumentForOcr(
        "document-17", PDF, (SuggestedPage(1, False), SuggestedPage(2, False)), threshold_percent=1,
    )

    execute(ports)

    assert_no_ocr_effects(ports)
    output.present.assert_called_once_with(OcrRejected("no_suggested_pages"))


@pytest.mark.parametrize("name", ["unknown", "GEMINI", " gemini ", "", None, "https://evil.example/v1"])
def test_unapproved_preset_is_rejected_before_loading_the_document(ports, name):
    documents, *_, output = ports

    execute(ports, preset=name)

    documents.load.assert_not_called()
    assert_no_ocr_effects(ports)
    output.present.assert_called_once_with(OcrRejected("invalid_preset"))


@pytest.mark.parametrize("presets", [
    (),
    (VisionPreset("gemini", "https://litellm.example/v1", "gemini-3.8-flash"),),  # missing key
    (SELECTED, VisionPreset("unused", "https://unused.example/v1", "m", " ")),      # any blank key
    (VisionPreset("gemini", "ftp://litellm.example/v1", "gemini-3.8-flash", "k"),),
    (SELECTED, SELECTED),
])
def test_invalid_trusted_catalogue_is_a_system_error_before_any_io(ports, presets):
    documents, *_, output = ports

    with pytest.raises(InvalidOcrConfiguration):
        execute(ports, presets=presets)

    documents.load.assert_not_called()
    assert_no_ocr_effects(ports)
    output.present.assert_not_called()


def test_missing_document_is_rejected_without_ocr_or_storage(ports):
    documents, *_, output = ports
    documents.load.return_value = DocumentNotFound()

    execute(ports, document_id="missing-document")

    documents.load.assert_called_once_with("missing-document")
    assert_no_ocr_effects(ports)
    output.present.assert_called_once_with(OcrRejected("document_not_found"))


def test_each_page_failure_is_recorded_and_later_pages_continue(ports):
    documents, renderer, ocr, attempts, output = ports
    documents.load.return_value = SavedDocumentForOcr("document-17", PDF, tuple(
        SuggestedPage(number, True) for number in (1, 2, 3, 4)
    ), threshold_percent=1)

    def render(*, pdf, page_number):
        if page_number == 2:
            raise PageRenderingError("private renderer details")
        return image(page_number)

    def read(*, image, preset):
        number = image.data.decode()[-1]
        if number == "1":
            raise OcrProviderError("private provider details")
        if number == "3":
            return OcrUnreadable()
        return OcrText("หน้าสี่")

    renderer.render.side_effect = render
    ocr.read.side_effect = read

    execute(ports)

    assert [call.kwargs["image"] for call in ocr.read.call_args_list] == [image(1), image(3), image(4)]
    assert attempts.append.call_args.args[0].pages == (
        OcrPage(1, True, "ocr_unavailable"),
        OcrPage(2, True, "ocr_unavailable"),
        OcrPage(3, True, "unreadable"),
        OcrPage(4, True, "extracted", "หน้าสี่", 0, 7, 0.0),
    )
    output.present.assert_called_once_with(OcrAttemptSaved("document-17", "attempt-5", (
        OcrPageResult(1, True, "ocr_unavailable"), OcrPageResult(2, True, "ocr_unavailable"),
        OcrPageResult(3, True, "unreadable"), OcrPageResult(4, True, "extracted", "หน้าสี่"),
    )))


def test_attempt_is_saved_even_when_every_page_is_unavailable(ports):
    _, _, ocr, attempts, output = ports
    ocr.read.side_effect = OcrProviderError("LiteLLM down")

    execute(ports)

    assert attempts.append.call_args.args[0].pages == (
        OcrPage(1, True, "ocr_unavailable"), OcrPage(3, True, "ocr_unavailable"),
    )
    output.present.assert_called_once_with(OcrAttemptSaved("document-17", "attempt-5", (
        OcrPageResult(1, True, "ocr_unavailable"), OcrPageResult(3, True, "ocr_unavailable"),
    )))


@pytest.mark.parametrize("result", [None, {"text": "x"}, OcrText(None), OcrText(4)])
def test_malformed_ocr_result_is_a_system_error_not_a_saved_page(ports, result):
    _, _, ocr, attempts, output = ports
    ocr.read.return_value = result

    with pytest.raises(InvalidOcrResult):
        execute(ports)

    ocr.read.assert_called_once()
    attempts.append.assert_not_called()
    output.present.assert_not_called()


def saved(**changes):
    facts = {"document_id": "document-17", "pdf": PDF,
             "pages": (SuggestedPage(1, True),), "threshold_percent": 1}
    return SavedDocumentForOcr(**{**facts, **changes})


@pytest.mark.parametrize("loaded", [
    None, {"document_id": "document-17"},
    saved(document_id="another-document"), saved(pdf=b""), saved(pdf="not bytes"),
    saved(threshold_percent=-1), saved(threshold_percent=float("nan")),
    saved(threshold_percent=True), saved(threshold_percent="1"),
    saved(pages=()), saved(pages=[SuggestedPage(1, True)]), saved(pages=(SuggestedPage(2, True),)),
    saved(pages=(SuggestedPage(1, True), SuggestedPage(1, False))),
    saved(pages=(SuggestedPage(1, "yes"),)), saved(pages=(object(),)),
])
def test_malformed_saved_document_facts_are_a_system_error_before_ocr(ports, loaded):
    documents, *_, output = ports
    documents.load.return_value = loaded

    with pytest.raises(InvalidOcrResult):
        execute(ports)

    assert_no_ocr_effects(ports)
    output.present.assert_not_called()


@pytest.mark.parametrize("acknowledgement", [None, "attempt-5", SavedOcrAttempt(""), SavedOcrAttempt(" "), SavedOcrAttempt(7)])
def test_malformed_storage_acknowledgement_cannot_emit_success(ports, acknowledgement):
    _, _, ocr, attempts, output = ports
    ocr.read.return_value = OcrText("อ่านได้")
    attempts.append.return_value = acknowledgement

    with pytest.raises(InvalidOcrResult):
        execute(ports)

    attempts.append.assert_called_once()
    output.present.assert_not_called()


# Tests of already-present propagation logic: no artificial red.
def test_storage_failure_propagates_without_success_or_retry(ports):
    _, _, ocr, attempts, output = ports
    ocr.read.return_value = OcrText("อ่านได้")
    failure = OcrAttemptStorageError("ack failed")
    attempts.append.side_effect = failure

    with pytest.raises(OcrAttemptStorageError) as caught:
        execute(ports)

    assert caught.value is failure
    attempts.append.assert_called_once()
    output.present.assert_not_called()


@pytest.mark.parametrize("failing_port", ["renderer", "ocr"])
def test_unexpected_page_error_propagates_stops_later_pages_and_saves_nothing(ports, failing_port):
    _, renderer, ocr, attempts, output = ports
    failure = RuntimeError("bug")
    ocr.read.return_value = OcrText("อ่านได้")
    (renderer.render if failing_port == "renderer" else ocr.read).side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        execute(ports)

    assert caught.value is failure
    assert renderer.render.call_count == 1
    attempts.append.assert_not_called()
    output.present.assert_not_called()


def test_document_source_failure_propagates_before_ocr(ports):
    documents, *_, output = ports
    documents.load.side_effect = DocumentSourceError("disk")

    with pytest.raises(DocumentSourceError):
        execute(ports)

    assert_no_ocr_effects(ports)
    output.present.assert_not_called()


def test_presentation_failure_does_not_repeat_ocr_or_storage(ports):
    _, renderer, ocr, attempts, output = ports
    ocr.read.return_value = OcrText("อ่านได้")
    output.present.side_effect = RuntimeError("presenter")

    with pytest.raises(RuntimeError):
        execute(ports)

    assert renderer.render.call_count == 2
    assert ocr.read.call_count == 2
    attempts.append.assert_called_once()
    output.present.assert_called_once()


def test_credentials_never_enter_the_attempt_or_the_outcome(ports):
    _, _, ocr, attempts, output = ports
    ocr.read.return_value = OcrText("อ่านได้")

    execute(ports)

    for value in (attempts.append.call_args.args[0], output.present.call_args.args[0]):
        assert "synthetic-selected-key" not in repr(vars(value)) + repr(value)
    assert not hasattr(attempts.append.call_args.args[0], "api_key")
