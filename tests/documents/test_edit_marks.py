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
    assert apply_edit_marks(TEXT, marked, struck=3, underlined=1) == (
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
