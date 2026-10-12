from dataclasses import replace
from unittest.mock import create_autospec

import pytest

from contexts.document_processing.v2.application.model_presets import (
    InvalidModelPresetCatalogue, ModelPresetCatalogue, VisionPreset,
)
from contexts.document_processing.v2.domain.documents.extraction import (
    DocumentExtraction, SourcePage,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import (
    InvalidRepairSourceResult, InvalidTextRepairResult, RepairSourceError, TextRepairError,
)
from contexts.document_processing.v2.domain.documents.text_quality import SuspiciousTextSpan
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.input_boundary import (
    RepairExtractedTextInputBoundary,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.interactor import (
    RepairExtractedTextInteractor,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.output_boundary import (
    RepairExtractedTextOutputBoundary,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import (
    LoadedRepairPage, RepairPageNotFound, RepairPageSource, TextRepairer,
    TextRepairNoChanges, TextRepairProposal, TextRepairUnrepairable,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.request import (
    RepairExtractedTextRequest,
)
from contexts.document_processing.v2.application.use_cases.repair_extracted_text.response import (
    RepairNoChanges, RepairRejected, RepairSuggested, RepairUnrepairable, SuggestedTextRepair,
)


@pytest.fixture
def ports():
    source = create_autospec(RepairPageSource, instance=True)
    source.load_page.return_value = RepairPageNotFound()
    repairer = create_autospec(TextRepairer, instance=True)
    repairer.propose.return_value = TextRepairNoChanges()
    return source, repairer, create_autospec(RepairExtractedTextOutputBoundary, instance=True)


def make_document(
    *, unreadable_threshold=100, suspicious_threshold=0, raw_text="กAข\ufffd\ufffd\ufffd\ufffd",
):
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "หน้าแรก"), SourcePage(2, "หน้าสอง"),
         SourcePage(3, raw_text)),
        threshold_percent=unreadable_threshold,
        suspicious_threshold_percent=suspicious_threshold,
    )
    assert isinstance(document, DocumentExtraction)
    return document


def execute(ports, *, request=None, catalogue=None, repository=None):
    source, repairer, output = ports
    if catalogue is None:
        catalogue = ModelPresetCatalogue((
            VisionPreset("unused-model", "https://first.example/v1", "first-model", "synthetic-unused-key"),
            VisionPreset("approved-model", "https://repair.example/v1", "text-model", "synthetic-repair-key"),
        ))
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import RepairRunRepository
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.records import SavedRepairRun

    if repository is None:
        repository = create_autospec(RepairRunRepository, instance=True)
        repository.save.return_value = SavedRepairRun("repair-run-19")
    boundary: RepairExtractedTextInputBoundary = RepairExtractedTextInteractor(
        source=source, repairer=repairer, output=output, catalogue=catalogue,
        repository=repository,
    )
    if request is None:
        request = RepairExtractedTextRequest("doc-review-17", 3, "approved-model")
    return boundary.execute(request)


def load_flagged_page(ports):
    document = make_document()
    ports[0].load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], document.raw_text_quality[2],
    )
    return document


def assert_exact_page_invocation(ports):
    source, repairer, _ = ports
    source.load_page.assert_called_once_with(document_id="doc-review-17", page_number=3)
    repairer.propose.assert_called_once_with(
        raw_text="กAข\ufffd\ufffd\ufffd\ufffd",
        spans=(
            SuspiciousTextSpan(1, 2, "latin_adjacent_to_thai"),
            SuspiciousTextSpan(3, 4, "replacement_character"),
            SuspiciousTextSpan(4, 5, "replacement_character"),
            SuspiciousTextSpan(5, 6, "replacement_character"),
            SuspiciousTextSpan(6, 7, "replacement_character"),
        ),
        preset=VisionPreset("approved-model", "https://repair.example/v1", "text-model", "synthetic-repair-key"),
    )


def test_validated_suggestion_is_saved_before_presenting_its_record_identity(ports):
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import RepairRunRepository
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.records import SavedRepairRun

    source, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal((SuggestedTextRepair(0, 3, "กาข"),))
    repository = create_autospec(RepairRunRepository, instance=True)
    repository.save.return_value = SavedRepairRun("repair-run-19")
    proposed = RepairSuggested(
        "doc-review-17", 3, (SuggestedTextRepair(0, 3, "กาข"),), "approved-model", "text-model",
    )
    repository.save.side_effect = lambda result: (
        output.present.assert_not_called() or SavedRepairRun("repair-run-19")
    )
    boundary = RepairExtractedTextInteractor(
        source=source, repairer=repairer, output=output, repository=repository,
        catalogue=ModelPresetCatalogue((VisionPreset(
            "approved-model", "https://repair.example/v1", "text-model", "synthetic-repair-key",
        ),)),
    )

    assert boundary.execute(RepairExtractedTextRequest("doc-review-17", 3, "approved-model")) is None

    repository.save.assert_called_once_with(proposed)
    output.present.assert_called_once_with(replace(proposed, repair_id="repair-run-19"))


@pytest.mark.parametrize("kind", ["no_changes", "unrepairable", "malformed", "rejected", "storage_error"])
def test_history_records_only_valid_model_outcomes_and_storage_failure_has_no_success(ports, kind):
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import RepairRunStorageError
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import RepairRunRepository
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.records import SavedRepairRun

    _, repairer, output = ports
    repository = create_autospec(RepairRunRepository, instance=True)
    repository.save.return_value = SavedRepairRun("repair-run-19")
    if kind != "rejected":
        load_flagged_page(ports)
    if kind == "unrepairable":
        repairer.propose.return_value = TextRepairUnrepairable()
    if kind == "malformed":
        repairer.propose.return_value = TextRepairProposal(())
        with pytest.raises(InvalidTextRepairResult):
            execute(ports, repository=repository)
        repository.save.assert_not_called()
        output.present.assert_not_called()
    elif kind == "storage_error":
        repository.save.side_effect = RepairRunStorageError("private storage details")
        with pytest.raises(RepairRunStorageError):
            execute(ports, repository=repository)
        output.present.assert_not_called()
        assert repairer.propose.call_count == 1
    else:
        execute(ports, repository=repository)
        if kind == "rejected":
            repository.save.assert_not_called()
            repairer.propose.assert_not_called()
        else:
            expected = RepairNoChanges if kind == "no_changes" else RepairUnrepairable
            repository.save.assert_called_once_with(expected(
                "doc-review-17", 3, "approved-model", "text-model",
            ))


def test_all_page_spans_are_sent_once_to_selected_model_and_no_changes_is_presented(ports):
    _, repairer, output = ports
    document = load_flagged_page(ports)
    repairer.propose.return_value = TextRepairNoChanges()

    assert execute(ports) is None

    assert_exact_page_invocation(ports)
    output.present.assert_called_once_with(RepairNoChanges(
        "doc-review-17", 3, "approved-model", "text-model", repair_id="repair-run-19",
    ))
    assert document.pages[2].text == "กAข\ufffd\ufffd\ufffd\ufffd"


def test_model_inability_is_presented_separately_from_no_changes(ports):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairUnrepairable()

    execute(ports)

    assert_exact_page_invocation(ports)
    output.present.assert_called_once_with(RepairUnrepairable(
        "doc-review-17", 3, "approved-model", "text-model", repair_id="repair-run-19",
    ))


def test_expanded_edit_is_presented_as_suggestion_without_overwriting_extraction(ports):
    _, repairer, output = ports
    document = load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal((SuggestedTextRepair(0, 3, "กาข"),))

    assert execute(ports) is None

    assert_exact_page_invocation(ports)
    output.present.assert_called_once_with(RepairSuggested(
        "doc-review-17", 3, (SuggestedTextRepair(0, 3, "กาข"),), "approved-model", "text-model",
        repair_id="repair-run-19",
    ))
    assert document.pages[2].text == "กAข\ufffd\ufffd\ufffd\ufffd"
    assert document.raw_text_quality[2].raw_text == "กAข\ufffd\ufffd\ufffd\ufffd"


@pytest.mark.parametrize("result", [
    object(), TextRepairProposal(()), TextRepairProposal(None),
    TextRepairProposal([SuggestedTextRepair(0, 3, "กาข")]),
    TextRepairProposal((object(),)),
    TextRepairProposal((SuggestedTextRepair(True, 2, "ก"),)),
    TextRepairProposal((SuggestedTextRepair(0, 3, None),)),
])
def test_malformed_model_result_never_becomes_a_success_or_business_rejection(ports, result):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = result

    with pytest.raises(InvalidTextRepairResult):
        execute(ports)

    assert_exact_page_invocation(ports)
    output.present.assert_not_called()


@pytest.mark.parametrize("edits,reason", [
    ((), "invalid_edits"),
    ((SuggestedTextRepair(1, 8, "private proposal"),), "out_of_bounds"),
    ((SuggestedTextRepair(0, 1, "private proposal"),), "outside_signals"),
    ((SuggestedTextRepair(0, 3, "private proposal"), SuggestedTextRepair(1, 2, "other")), "overlapping_edits"),
])
def test_invalid_proposal_keeps_safe_domain_reason_without_recording_history(ports, edits, reason):
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import RepairRunRepository

    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal(edits)
    repository = create_autospec(RepairRunRepository, instance=True)

    with pytest.raises(InvalidTextRepairResult) as caught:
        execute(ports, repository=repository)

    assert caught.value.reason == reason
    assert_exact_page_invocation(ports)
    repository.save.assert_not_called()
    output.present.assert_not_called()


def test_outside_signal_failure_carries_only_counts_and_rejected_offsets_in_proposed_order(ports):
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import RepairRunRepository

    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal((
        SuggestedTextRepair(3, 4, "valid private replacement"),
        SuggestedTextRepair(2, 3, "private rejected replacement"),
        SuggestedTextRepair(0, 1, "another private replacement"),
    ))
    repository = create_autospec(RepairRunRepository, instance=True)

    with pytest.raises(InvalidTextRepairResult) as caught:
        execute(ports, repository=repository)

    assert caught.value.reason == "outside_signals"
    details = caught.value.proposal_diagnostic
    assert details.edit_count == 3
    assert details.outside_signal_edit_count == 2
    assert details.signal_count == 5
    assert details.outside_signal_edit_ranges == ((2, 3), (0, 1))
    assert details.signal_ranges == ((1, 2), (3, 4), (4, 5), (5, 6), (6, 7))
    assert "private" not in repr(details)
    assert_exact_page_invocation(ports)
    repository.save.assert_not_called()
    output.present.assert_not_called()


def test_outside_signal_diagnostic_keeps_total_counts_but_only_first_ten_ranges(ports):
    source, repairer, output = ports
    document = make_document(raw_text="กAข" * 15)
    source.load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], document.raw_text_quality[2],
    )
    repairer.propose.return_value = TextRepairProposal(tuple(
        SuggestedTextRepair(3 * index, 3 * index + 1, "private replacement") for index in range(15)
    ))

    with pytest.raises(InvalidTextRepairResult) as caught:
        execute(ports)

    details = caught.value.proposal_diagnostic
    assert (details.edit_count, details.outside_signal_edit_count, details.signal_count) == (15, 15, 15)
    assert details.outside_signal_edit_ranges == (
        (0, 1), (3, 4), (6, 7), (9, 10), (12, 13), (15, 16), (18, 19), (21, 22), (24, 25), (27, 28),
    )
    assert details.signal_ranges == (
        (1, 2), (4, 5), (7, 8), (10, 11), (13, 14), (16, 17), (19, 20), (22, 23), (25, 26), (28, 29),
    )
    output.present.assert_not_called()
    assert repairer.propose.call_count == 1


@pytest.mark.parametrize("start,end", [(-1, 2), (1, 1), (2, 1), (1, 8)])
def test_edit_range_must_be_nonempty_and_within_raw_codepoint_bounds(ports, start, end):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal((SuggestedTextRepair(start, end, "แก้"),))

    with pytest.raises(InvalidTextRepairResult):
        execute(ports)

    assert_exact_page_invocation(ports)
    output.present.assert_not_called()


@pytest.mark.parametrize("start,end", [(0, 1), (2, 3)])
def test_expansion_must_overlap_a_signal_not_merely_touch_its_boundary(ports, start, end):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal((SuggestedTextRepair(start, end, "แก้"),))

    with pytest.raises(InvalidTextRepairResult):
        execute(ports)

    assert_exact_page_invocation(ports)
    output.present.assert_not_called()


@pytest.mark.parametrize("edits", [
    (SuggestedTextRepair(0, 3, "กาข"), SuggestedTextRepair(1, 2, "า")),
    (SuggestedTextRepair(1, 2, "า"), SuggestedTextRepair(1, 2, "อื่น")),
    (SuggestedTextRepair(3, 5, "แก้"), SuggestedTextRepair(0, 4, "คำ")),
])
def test_overlapping_or_duplicate_edits_are_rejected_even_when_unsorted(ports, edits):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal(edits)

    with pytest.raises(InvalidTextRepairResult):
        execute(ports)

    assert_exact_page_invocation(ports)
    output.present.assert_not_called()


# Coverage of already-present logic; no artificial red/green cycle.
def test_adjacent_edits_allow_deletion_and_preserve_proposed_order(ports):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairProposal((
        SuggestedTextRepair(3, 4, ""), SuggestedTextRepair(0, 3, "กาข"),
    ))

    execute(ports)

    assert_exact_page_invocation(ports)
    output.present.assert_called_once_with(RepairSuggested(
        "doc-review-17", 3,
        (SuggestedTextRepair(3, 4, ""), SuggestedTextRepair(0, 3, "กาข")),
        "approved-model", "text-model", repair_id="repair-run-19",
    ))


@pytest.mark.parametrize("failure_type", [InvalidTextRepairResult, TextRepairError])
@pytest.mark.parametrize("arguments", [(), ("private model details",), ("private model details", "extra")])
def test_model_contract_failure_preserves_existing_exception_arguments_and_identity(ports, arguments, failure_type):
    _, repairer, output = ports
    load_flagged_page(ports)
    failure = failure_type(*arguments)
    repairer.propose.side_effect = failure

    with pytest.raises(failure_type) as caught:
        execute(ports)

    assert caught.value is failure
    assert caught.value.args == arguments
    assert caught.value.reason is None
    if isinstance(failure, TextRepairError):
        assert caught.value.http_status is None
    assert_exact_page_invocation(ports)
    output.present.assert_not_called()


@pytest.mark.parametrize("failure", [TextRepairError("provider unavailable"), KeyError("unexpected")])
def test_model_failure_propagates_without_retry_or_outcome(ports, failure):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.side_effect = failure

    with pytest.raises(type(failure)) as caught:
        execute(ports)

    assert caught.value is failure
    assert_exact_page_invocation(ports)
    output.present.assert_not_called()


def test_invalid_shared_catalogue_propagates_shared_error_before_any_io(ports):
    source, repairer, output = ports
    catalogue = ModelPresetCatalogue((
        VisionPreset("duplicate", "https://first.example/v1", "first-model", "synthetic-first-key"),
        VisionPreset("duplicate", "https://second.example/v1", "second-model", "synthetic-second-key"),
    ))

    with pytest.raises(InvalidModelPresetCatalogue):
        execute(ports, catalogue=catalogue)

    source.load_page.assert_not_called()
    repairer.propose.assert_not_called()
    output.present.assert_not_called()


def test_presentation_failure_does_not_repeat_the_model_call(ports):
    _, repairer, output = ports
    load_flagged_page(ports)
    repairer.propose.return_value = TextRepairNoChanges()
    failure = RuntimeError("presentation unavailable")
    output.present.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        execute(ports)

    assert caught.value is failure
    assert_exact_page_invocation(ports)
    output.present.assert_called_once_with(RepairNoChanges(
        "doc-review-17", 3, "approved-model", "text-model", repair_id="repair-run-19",
    ))


def test_thai_mark_edits_use_codepoint_offsets_without_normalizing_raw_text(ports):
    source, repairer, output = ports
    document = make_document(raw_text="กิิิAข")
    source.load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], document.raw_text_quality[2],
    )
    repairer.propose.return_value = TextRepairProposal((SuggestedTextRepair(0, 4, "กิ"),))

    execute(ports)

    repairer.propose.assert_called_once_with(
        raw_text="กิิิAข",
        spans=(
            SuspiciousTextSpan(1, 2, "thai_mark_sequence"),
            SuspiciousTextSpan(2, 3, "thai_mark_sequence"),
            SuspiciousTextSpan(3, 4, "thai_mark_sequence"),
            SuspiciousTextSpan(4, 5, "latin_adjacent_to_thai"),
        ),
        preset=VisionPreset("approved-model", "https://repair.example/v1", "text-model", "synthetic-repair-key"),
    )
    output.present.assert_called_once_with(RepairSuggested(
        "doc-review-17", 3, (SuggestedTextRepair(0, 4, "กิ"),), "approved-model", "text-model",
        repair_id="repair-run-19",
    ))
    assert document.pages[2].text == "กิิิAข"


def test_unapproved_repair_preset_is_rejected_before_source_or_model_io(ports):
    source, repairer, output = ports

    execute(ports, request=RepairExtractedTextRequest(
        "doc-review-17", 3, "https://unapproved.example/private",
    ))

    output.present.assert_called_once_with(RepairRejected("invalid_preset"))
    source.load_page.assert_not_called()
    repairer.propose.assert_not_called()


@pytest.mark.parametrize("document_id,page_number", [
    ("", 3), (" ", 3), (None, 3), ("doc-review-17", 0),
    ("doc-review-17", -1), ("doc-review-17", True), ("doc-review-17", "3"),
])
def test_invalid_page_selection_is_rejected_without_io(ports, document_id, page_number):
    source, repairer, output = ports

    execute(ports, request=RepairExtractedTextRequest(document_id, page_number, "approved-model"))

    output.present.assert_called_once_with(RepairRejected("invalid_request"))
    source.load_page.assert_not_called()
    repairer.propose.assert_not_called()


def test_missing_document_or_page_is_rejected_without_model_invocation(ports):
    source, repairer, output = ports
    source.load_page.return_value = RepairPageNotFound()

    execute(ports)

    source.load_page.assert_called_once_with(document_id="doc-review-17", page_number=3)
    output.present.assert_called_once_with(RepairRejected("page_not_found"))
    repairer.propose.assert_not_called()


@pytest.mark.parametrize("fault", ["document", "page", "undeclared", "pending"])
def test_invalid_or_misbound_source_cannot_reach_model_or_presenter(ports, fault):
    source, repairer, output = ports
    document = make_document()
    page = document.pages[2]
    loaded = LoadedRepairPage("doc-review-17", page, document.raw_text_quality[2])
    if fault == "document":
        loaded = replace(loaded, document_id="doc-other-88")
    elif fault == "page":
        loaded = replace(loaded, page=replace(page, number=2))
    elif fault == "pending":
        loaded = replace(loaded, page=replace(page, status="pending_fallback"))
    else:
        loaded = object()
    source.load_page.return_value = loaded

    with pytest.raises(InvalidRepairSourceResult):
        execute(ports)

    repairer.propose.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("fault", ["report_page", "text", "type", "flag", "method", "parser_failed"])
def test_incoherent_raw_report_is_a_contract_error_not_a_repair_decision(ports, fault):
    source, repairer, output = ports
    document = make_document()
    page, report = document.pages[2], document.raw_text_quality[2]
    if fault == "report_page":
        report = replace(report, number=2)
    elif fault == "text":
        report = replace(report, raw_text="ข้อความของอีกหน้า")
    elif fault == "type":
        report = object()
    elif fault == "flag":
        report = replace(report, flagged=1)
    elif fault == "parser_failed":
        page = replace(page, status="failed")
    else:
        page = replace(page, method="unknown-method")
    source.load_page.return_value = LoadedRepairPage("doc-review-17", page, report)

    with pytest.raises(InvalidRepairSourceResult):
        execute(ports)

    repairer.propose.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("raw_text,spans", [
    (None, (SuspiciousTextSpan(1, 2, "latin_adjacent_to_thai"),)),
    ("กAข", ()),
    ("กAข", [SuspiciousTextSpan(1, 2, "latin_adjacent_to_thai")]),
    ("กAข", (SuspiciousTextSpan(-1, 2, "latin_adjacent_to_thai"),)),
    ("กAข", (SuspiciousTextSpan(1, 4, "latin_adjacent_to_thai"),)),
    ("กAข", (SuspiciousTextSpan(True, 2, "latin_adjacent_to_thai"),)),
    ("กAข", (SuspiciousTextSpan(1, 1, "latin_adjacent_to_thai"),)),
    ("กAข", (SuspiciousTextSpan(1, 2, "unknown-reason"),)),
])
def test_invalid_raw_text_or_spans_never_reach_the_model(ports, raw_text, spans):
    source, repairer, output = ports
    document = make_document()
    page = replace(document.pages[2], text=raw_text)
    report = replace(document.raw_text_quality[2], raw_text=raw_text, spans=spans)
    source.load_page.return_value = LoadedRepairPage("doc-review-17", page, report)

    with pytest.raises(InvalidRepairSourceResult):
        execute(ports)

    repairer.propose.assert_not_called()
    output.present.assert_not_called()


def test_vision_page_is_rejected_even_when_retained_raw_report_is_flagged(ports):
    source, repairer, output = ports
    document = make_document(unreadable_threshold=50)
    document = document.complete_fallback(
        page_number=3, text="ข้อความอ่านได้", preset_name="vision-approved", model="vision-model",
    )
    assert isinstance(document, DocumentExtraction)
    source.load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], document.raw_text_quality[2],
    )

    assert execute(ports) is None

    source.load_page.assert_called_once_with(document_id="doc-review-17", page_number=3)
    output.present.assert_called_once_with(RepairRejected("vision_page"))
    repairer.propose.assert_not_called()


def test_failed_vision_attempt_is_still_ineligible_for_text_repair(ports):
    source, repairer, output = ports
    document = make_document(unreadable_threshold=50)
    document = document.fail_fallback(
        page_number=3, code="fallback_unavailable",
        preset_name="vision-approved", model="vision-model",
    )
    assert isinstance(document, DocumentExtraction)
    source.load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], document.raw_text_quality[2],
    )

    execute(ports)

    output.present.assert_called_once_with(RepairRejected("vision_page"))
    repairer.propose.assert_not_called()


def test_assessed_but_unflagged_page_is_rejected_without_calling_model(ports):
    source, repairer, output = ports
    document = make_document(suspicious_threshold=100)
    source.load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], document.raw_text_quality[2],
    )

    execute(ports)

    output.present.assert_called_once_with(RepairRejected("page_not_flagged"))
    repairer.propose.assert_not_called()


def test_source_failure_propagates_without_model_invocation_or_outcome(ports):
    source, repairer, output = ports
    failure = RepairSourceError("source unavailable")
    source.load_page.side_effect = failure

    with pytest.raises(RepairSourceError) as caught:
        execute(ports)

    assert caught.value is failure
    source.load_page.assert_called_once_with(document_id="doc-review-17", page_number=3)
    repairer.propose.assert_not_called()
    output.present.assert_not_called()


def test_unassessed_parser_page_is_rejected_without_calling_model(ports):
    source, repairer, output = ports
    document = make_document(suspicious_threshold=None)
    source.load_page.return_value = LoadedRepairPage(
        "doc-review-17", document.pages[2], None,
    )

    execute(ports)

    output.present.assert_called_once_with(RepairRejected("not_assessed"))
    repairer.propose.assert_not_called()
