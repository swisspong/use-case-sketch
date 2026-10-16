"""Struck/underlined text: pixel detection and mark verification (no DB)."""

import io

from PIL import Image

from app.modules.documents.adapters.edit_mark_detector import (
    draw_edit_boxes,
    find_edit_lines,
)
from app.modules.documents.rules import apply_edit_marks
from tests.helpers import page, words


def test_strike_and_underline_are_found_with_their_extent():
    def paint(draw):
        right = words(draw, 100, 200, 12)
        draw.rectangle([100, 209, right, 211], fill=0)  # through the middle
        right = words(draw, 100, 400, 8)
        draw.rectangle([100, 424, right, 426], fill=0)  # under the baseline
        words(draw, 100, 600, 20)  # plain text

    lines = find_edit_lines(page(paint))
    assert [(line.kind, line.left, line.top) for line in lines] == [
        ("strike", 100, 209),
        ("underline", 100, 424),
    ]


def test_borders_rules_and_short_strokes_are_not_edit_marks():
    def paint(draw):
        words(draw, 100, 200, 30)
        draw.rectangle([53, 224, 947, 226], fill=0)  # row border across the whole cell
        words(draw, 100, 400, 8)
        draw.rectangle([100, 424, 700, 426], fill=0)  # rule running far past the text
        draw.rectangle([300, 600, 900, 602], fill=0)  # rule with no text on it
        words(draw, 100, 800, 2)
        draw.rectangle([100, 824, 120, 826], fill=0)  # stroke shorter than a word

    assert find_edit_lines(page(paint)) == []


def test_unreadable_image_has_no_marks_and_boxes_are_drawn_in_colour():
    assert find_edit_lines(b"\x89PNG") == []

    def paint(draw):
        right = words(draw, 100, 200, 12)
        draw.rectangle([100, 209, right, 211], fill=0)

    png = page(paint)
    boxed = Image.open(io.BytesIO(draw_edit_boxes(png, find_edit_lines(png))))
    colours = {colour for _, colour in boxed.getcolors(1 << 16)}
    assert (230, 0, 0) in colours  # red: struck
    assert (0, 80, 255) not in colours  # no underline box


TEXT = """| ฉบับที่ ๖ โดยและพวกเรา | ร้อยละ ๔๓ |
| --- | --- |
ยั่งยืนอย่างมาก
ถึงร้อยละ ๔๓"""


def test_marks_are_copied_onto_the_text_keeping_its_spacing():
    # The mark pass re-flowed lines and dropped the table spacing; only marks move over.
    marked = "| ฉบับที่ ๖ ~~โดย~~++และพวกเรา++ | ร้อยละ ๔๓ |\n|---|---|\nยั่งยืน~~อย่างมาก~~ ~~ถึงร้อยละ ๔๓~~"
    # Two struck boxes on following lines are one run once their marks are joined.
    assert apply_edit_marks(TEXT, marked, struck=2, underlined=1) == (
        "| ฉบับที่ ๖ ~~โดย~~++และพวกเรา++ | ร้อยละ ๔๓ |\n| --- | --- |\n"
        "ยั่งยืน~~อย่างมาก\nถึงร้อยละ ๔๓~~"
    )


def test_marks_are_rejected_unless_counts_and_text_match_exactly():
    good = (
        "| ฉบับที่ ๖ ~~โดย~~และพวกเรา | ร้อยละ ๔๓ |\n| --- | --- |\nยั่งยืนอย่างมาก\nถึงร้อยละ ๔๓"
    )
    assert apply_edit_marks(TEXT, good, struck=1, underlined=0)
    # One detected line left unmarked, or a mark the detector did not see: rejected.
    assert apply_edit_marks(TEXT, good, struck=2, underlined=0) is None
    assert apply_edit_marks(TEXT, good, struck=1, underlined=1) is None
    changed = good.replace("๔๓", "๔๙", 1)
    assert apply_edit_marks(TEXT, changed, struck=1, underlined=0) is None
    assert apply_edit_marks("ภาษา C++", "ภาษา ~~C++~~", struck=1, underlined=0) is None


def test_marking_box_by_box_or_run_by_run_counts_the_same():
    per_box = "| ฉบับที่ ๖ โดยและพวกเรา | ร้อยละ ๔๓ |\n| --- | --- |\n~~ยั่งยืนอย่างมาก~~\n~~ถึงร้อยละ ๔๓~~"
    per_run = (
        "| ฉบับที่ ๖ โดยและพวกเรา | ร้อยละ ๔๓ |\n| --- | --- |\n~~ยั่งยืนอย่างมาก\nถึงร้อยละ ๔๓~~"
    )
    expected = apply_edit_marks(TEXT, per_run, struck=1, underlined=0)
    assert (
        expected and apply_edit_marks(TEXT, per_box, struck=1, underlined=0) == expected
    )
    # Seen live: an underline run swallowed a struck word, leaving one strike run short.
    assert apply_edit_marks(TEXT, per_run, struck=2, underlined=0) is None


def test_lines_continuing_a_passage_on_the_next_text_line_form_one_run():
    def paint(draw):
        right = words(draw, 100, 200, 30)  # line 1: struck from mid-line to its end
        draw.rectangle([280, 209, right, 211], fill=0)
        right = words(draw, 100, 250, 30)  # line 2: struck from its start to mid-line
        draw.rectangle([100, 259, 400, 261], fill=0)
        words(draw, 100, 400, 30)  # line 3: struck mid-line only
        draw.rectangle([280, 409, 500, 411], fill=0)
        words(
            draw, 100, 450, 30
        )  # line 4: struck from its start; line 3 did not reach the end
        draw.rectangle([100, 459, 300, 461], fill=0)

    lines = find_edit_lines(page(paint))
    assert [line.top for line in lines] == [209, 259, 409, 459]
    runs = [line.run for line in lines]
    assert runs[0] == runs[1] and len(set(runs)) == 3
