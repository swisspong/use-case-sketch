"""Pass-2 OCR structuring may only re-lay out pass-1 text (pure rule, no DB)."""

import pytest

from app.modules.documents.rules import same_content

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
