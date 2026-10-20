"""Regression examples from the historical backend v3 detector."""

import pytest

from app.modules.documents.rules import assess_quality
from app.modules.documents.text_quality import (
    assess_problem_characters,
    detect_text_signals,
)

T = {
    "max_thai_percent": 100,
    "max_garbled_thai_percent": 5,
    "min_text_chars": 0,
    "max_image_percent": 100,
}


@pytest.mark.parametrize(
    "text,count,reasons",
    [
        ("ทีC เชืMอ", 2, {"latin_adjacent_to_thai"}),
        ("ทีÇ", 1, {"latin_adjacent_to_thai"}),
        ("ก่้", 2, {"thai_mark_sequence"}),
        ("กิิ", 2, {"thai_mark_sequence"}),
        ("่่", 2, {"thai_mark_sequence"}),
        ("เปิ ดเผย", 1, {"split_thai_syllable"}),
        ("ผู้ป่ วย", 1, {"split_thai_syllable"}),
        ("ฝ่ าย", 1, {"split_thai_syllable"}),
        ("เปลี่ ยน", 1, {"split_thai_syllable"}),
        (
            "a\ufffd\x01\ue000\U000f0000",
            4,
            {"replacement_character", "unexpected_control", "private_use_character"},
        ),
    ],
)
def test_backend_v3_signals_drive_the_active_quality_metric(text, count, reasons):
    original = text
    p = assess_problem_characters(text)
    assert p.count == count
    assert {s.reason for s in p.spans} == reasons
    assert text == original
    q = assess_quality(text, 0, T)
    assert q["garbled_thai_percent"] == round(
        100 * count / sum(not c.isspace() for c in text), 2
    )
    assert q["failed"] == ["max_garbled_thai_percent"]


@pytest.mark.parametrize(
    "text",
    [
        "ผู้ป่วย สิทธิ์ กิ๊บ ปุ๋ย",
        "ภาษาไทย\nCOVID-19\tB12\r\n",
        "ได้ เนื้อ",
        "แก่ บ้าน",
        "ที่ เป็น",
        "แพทย์ กรม",
        "กรณี HI",
        "สิบปี ",
        "แต่ 30",
        "C฿",
        "C๑",
        "C๏",
        "",
        " \n\t",
    ],
)
def test_valid_thai_and_english_codes_do_not_trigger_garbled_text(text):
    assert detect_text_signals(text).spans == ()
    assert assess_quality(text, 0, T)["passed"]


def test_overlapping_signals_count_each_non_whitespace_position_once():
    problems = assess_problem_characters("่่ ป่ วย")
    assert problems.count == 3
    assert problems.non_whitespace_count == 6
    assert problems.percent == 50
    assert problems.exceeds(49) and not problems.exceeds(50)


@pytest.mark.parametrize(
    "text,images,thresholds,failed",
    [
        (
            "ก1",
            80,
            {"max_thai_percent": 50, "min_text_chars": 2, "max_image_percent": 80},
            [],
        ),
        ("กก1", 80, {"max_thai_percent": 50}, ["max_thai_percent"]),
        ("ทีC เชืMอ", 0, {"max_garbled_thai_percent": 25}, []),
        ("ทีC เชืMอ", 0, {"max_garbled_thai_percent": 24}, ["max_garbled_thai_percent"]),
        ("abc", 81, {"max_image_percent": 80}, ["max_image_percent"]),
        ("abc", 0, {"min_text_chars": 4}, ["min_text_chars"]),
        (
            "ก่้",
            81,
            {
                "max_thai_percent": 50,
                "max_garbled_thai_percent": 5,
                "min_text_chars": 4,
                "max_image_percent": 80,
            },
            [
                "max_thai_percent",
                "max_garbled_thai_percent",
                "min_text_chars",
                "max_image_percent",
            ],
        ),
    ],
)
def test_any_one_criterion_suggests_ocr_and_exact_boundary_passes(
    text, images, thresholds, failed
):
    q = assess_quality(text, images, T | thresholds)
    assert q["failed"] == failed
    assert q["passed"] is (not failed)
