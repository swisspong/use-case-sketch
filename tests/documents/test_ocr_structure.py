"""OCR text rules: pass 2 may only re-lay out pass 1, and pass-1 markup is flattened (no DB)."""

import pytest

from app.modules.documents.rules import repair_tables, same_content, strip_markup

# Shapes taken from a real page: a layout frame (agenda grid) holding a data table.
PLAIN = """๔๑
วาระที่
มติที่ประชุม/ข้อสั่งการ
หน่วยงาน
ที่รับผิดชอบ
ฝ่ายเลขานุการ มีความเห็น ดังนี้
ให้ กรุงเทพมหานคร ดำเนินการ
๔.๘.๔ โครงการบรรเทาอุทกภัยพื้นที่ลุ่มน้ำเพชรบุรีตอนล่าง
• ที่ตั้งโครงการ : จุดรับน้ำอยู่ที่ตำบลท่าไม้รวก อำเภอท่ายาง
ผลการวิเคราะห์เชิงเศรษฐศาสตร์ ปี ๒๕๖๘
๑.๑ ด้านการเกษตร ๗๒.๙๐
๑.๒ ด้านบรรเทาอุทกภัย ๑,๐๘๑.๘๔
หมายเหตุ : ๑) ณ อัตราคิดลด (Discount rate) ที่ร้อยละ ๗
สำเนาถูกต้อง
สรุปมติและข้อสั่งการในการประชุม กนช. ครั้งที่ ๕/๒๕๖๘"""

STRUCTURED = """๔๑

มติที่ประชุม/ข้อสั่งการ: ฝ่ายเลขานุการ มีความเห็น ดังนี้
ให้ กรุงเทพมหานคร ดำเนินการ

วาระที่: ๔.๘.๔
มติที่ประชุม/ข้อสั่งการ: โครงการบรรเทาอุทกภัยพื้นที่ลุ่มน้ำเพชรบุรีตอนล่าง
• ที่ตั้งโครงการ : จุดรับน้ำอยู่ที่ตำบลท่าไม้รวก อำเภอท่ายาง

| ผลการวิเคราะห์เชิงเศรษฐศาสตร์ | ปี ๒๕๖๘ |
| --- | :---: |
| ๑.๑ ด้านการเกษตร | ๗๒.๙๐ |
| ๑.๒ ด้านบรรเทาอุทกภัย | ๑,๐๘๑.๘๔ |

หมายเหตุ : ๑) ณ อัตราคิดลด (Discount rate) ที่ร้อยละ ๗

สรุปมติและข้อสั่งการในการประชุม กนช. ครั้งที่ ๕/๒๕๖๘
สำเนาถูกต้อง"""


def test_relayout_with_tables_labels_dropped_header_and_reorder_is_accepted():
    assert same_content(PLAIN, STRUCTURED)
    assert same_content(PLAIN, PLAIN)


@pytest.mark.parametrize(
    "old,new",
    [
        ("๗๒.๙๐", "๓๒.๙๐"),  # misread digit seen in single-pass table prompts
        ("ท่าไม้รวก", "ท่ายาง"),  # name replaced by a nearby word
        ("ให้ กรุงเทพมหานคร ดำเนินการ\n", ""),  # content line dropped
        ("| ๑.๒ ด้านบรรเทาอุทกภัย | ๑,๐๘๑.๘๔ |\n", ""),  # table row dropped
        ("\n| ๑.๑", "<br>| ๑.๑"),  # HTML is added text
        ("๔๑\n", "# ๔๑\n"),  # heading markup is added text
        ("วาระที่: ๔.๘.๔", "Agenda: ๔.๘.๔"),  # label not taken from the page
    ],
)
def test_any_changed_added_or_dropped_text_is_rejected(old, new):
    assert old in STRUCTURED
    assert not same_content(PLAIN, STRUCTURED.replace(old, new))


def test_colon_text_on_the_page_is_not_treated_as_a_label():
    # "หมายเหตุ :" is page text, so dropping what follows it cannot hide behind a label.
    structured = STRUCTURED.replace(
        "หมายเหตุ : ๑) ณ อัตราคิดลด (Discount rate) ที่ร้อยละ ๗", "หมายเหตุ :"
    )
    assert not same_content(PLAIN, structured)


def test_dropped_header_run_must_hold_a_label_and_stay_short():
    unlabelled = STRUCTURED.replace("วาระที่: ", "").replace("มติที่ประชุม/ข้อสั่งการ: ", "")
    assert not same_content(PLAIN, unlabelled)
    long_line = "ก" * 81
    plain = PLAIN.replace("หน่วยงาน\n", f"หน่วยงาน\n{long_line}\n")
    assert not same_content(plain, STRUCTURED)


# Pass 1 ignoring "No markdown" (seen with PDF input and ultra_high detail): the frame as a
# pipe table, cells joined with <br>, and the data table nested inside a cell.
MARKUP = """๔๑
| วาระที่ | มติที่ประชุม/ข้อสั่งการ | หน่วยงาน<br>ที่รับผิดชอบ |
|---|---|---|
| | ฝ่ายเลขานุการ มีความเห็น ดังนี้<br>ให้ กรุงเทพมหานคร ดำเนินการ | |
| ๔.๘.๔ | โครงการบรรเทาอุทกภัยพื้นที่ลุ่มน้ำเพชรบุรีตอนล่าง<br>• ที่ตั้งโครงการ : จุดรับน้ำอยู่ที่ตำบลท่าไม้รวก อำเภอท่ายาง<br><br>| ผลการวิเคราะห์เชิงเศรษฐศาสตร์ | ปี ๒๕๖๘ |<br>| :--- | :---: |<br>| ๑.๑ ด้านการเกษตร | ๗๒.๙๐ |<br>| ๑.๒ ด้านบรรเทาอุทกภัย | ๑,๐๘๑.๘๔ |<br><br>หมายเหตุ : ๑) ณ อัตราคิดลด (Discount rate) ที่ร้อยละ ๗ | |
สำเนาถูกต้อง
สรุปมติและข้อสั่งการในการประชุม กนช. ครั้งที่ ๕/๒๕๖๘"""


def test_text_without_markup_is_returned_unchanged():
    for text in (PLAIN, "  ย่อหน้า\n\nบรรทัด  ", "a < b และ x > y", ""):
        assert strip_markup(text) == text


def test_pass_one_markup_is_flattened_into_plain_lines():
    plain = strip_markup(MARKUP)
    assert "|" not in plain and "<br" not in plain and "---" not in plain
    assert plain.splitlines()[:5] == [
        "๔๑",
        "วาระที่",
        "มติที่ประชุม/ข้อสั่งการ",
        "หน่วยงาน",
        "ที่รับผิดชอบ",
    ]
    assert "๑.๑ ด้านการเกษตร\n๗๒.๙๐" in plain
    # Flattened, it is a transcription that the structuring pass can be checked against.
    assert same_content(plain, STRUCTURED)


def test_inline_tags_are_removed_but_their_text_stays():
    text = "(โรคจากรังสีแตกตัว)<sup>๓</sup> และ <b>ซีเซียม-๑๓๗</b><SUP>๔</SUP>"
    assert strip_markup(text) == "(โรคจากรังสีแตกตัว)๓ และ ซีเซียม-๑๓๗๔"


def test_html_tables_from_pass_one_are_flattened_like_pipe_tables():
    html = """๔๑
<table>
  <tr>
    <td>วาระที่</td>
    <td>มติที่ประชุม/ข้อสั่งการ</td>
    <td colspan="1">หน่วยงาน<br>ที่รับผิดชอบ</td>
  </tr>
  <tr>
    <td></td>
    <td>
ฝ่ายเลขานุการ มีความเห็น ดังนี้<br>
ให้ กรุงเทพมหานคร ดำเนินการ
    </td>
  </tr>
</table>"""
    assert strip_markup(html) == strip_markup(MARKUP.split("\n| ๔.๘.๔")[0])


def test_missing_table_separator_row_is_inserted_after_the_header():
    # Seen with reasoning_effort "low": the table without its separator row.
    broken = STRUCTURED.replace("| --- | :---: |\n", "")
    repaired = repair_tables(broken)
    assert "| ผลการวิเคราะห์เชิงเศรษฐศาสตร์ | ปี ๒๕๖๘ |\n| --- | --- |\n| ๑.๑" in repaired
    assert repaired.replace("| --- | --- |\n", "") == broken
    two = "| a | b | c |\n| 1 | 2 | 3 |\n\nข้อความ\n\n| x |\n| y |"
    assert repair_tables(two) == (
        "| a | b | c |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n\nข้อความ\n\n| x |\n| --- |\n| y |"
    )


def test_well_formed_tables_and_plain_text_are_left_unchanged():
    for text in (STRUCTURED, PLAIN, "| only | header |\n|---|---|", "a | b ไม่ใช่ตาราง"):
        assert repair_tables(text) == text
