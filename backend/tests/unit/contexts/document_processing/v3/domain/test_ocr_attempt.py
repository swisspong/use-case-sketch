"""Agreed domain seam: OcrAttempt page transitions, unreachable via the Interactor."""

import pytest

from contexts.document_processing.v3.domain.documents.ocr_attempt import (
    InvalidOcrTransition, OcrAttempt, OcrPage, SuggestedPage,
)


def attempt():
    return OcrAttempt.start(
        document_id="document-17", saved_pages=(SuggestedPage(1, True), SuggestedPage(2, False)),
        requested=(1, 2), preset_name="gemini", model="gemini-3.8-flash", threshold_percent=1,
    )


RECORDS = {
    "text": lambda attempt, number: attempt.record_text(page_number=number, text="อ่านได้"),
    "unreadable": lambda attempt, number: attempt.record_unreadable(page_number=number),
    "unavailable": lambda attempt, number: attempt.record_unavailable(page_number=number),
}


@pytest.mark.parametrize("first", RECORDS)
@pytest.mark.parametrize("second", RECORDS)
def test_terminal_page_cannot_be_recorded_again(first, second):
    terminal = RECORDS[first](attempt(), 1)

    assert RECORDS[second](terminal, 1) == InvalidOcrTransition("invalid_transition")
    assert terminal.pages[1] == OcrPage(2, False, "pending")
    assert terminal.pages[0].status != "pending"


@pytest.mark.parametrize("record", RECORDS)
@pytest.mark.parametrize("number", [3, 0, True, "1", 1.0, None])
def test_page_outside_the_attempt_or_non_integer_number_is_rejected(record, number):
    pending = attempt()

    assert RECORDS[record](pending, number) == InvalidOcrTransition("invalid_transition")
    assert pending.pages == (OcrPage(1, True, "pending"), OcrPage(2, False, "pending"))
