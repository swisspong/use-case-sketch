# Notes: แนวคิดปรับปรุง PDF text extraction

## Version handoff สำหรับ session ถัดไป

- **v1 baseline:** `backend/src/contexts/document_processing/v1/` — ชุดปัจจุบันที่เก็บไว้เปรียบเทียบ ไม่เพิ่ม improve ลงใน v1
- **v2 working copy:** `backend/src/contexts/document_processing/v2/` — detector แบบ report-only ต่อ CLI/config JSON/storage/summary แล้ว พร้อม unit และ integration tests; ยังไม่มี LLM/OCR หรือ force-fallback flag
- Tests แยกใน `backend/tests/{unit,integration}/contexts/document_processing/{v1,v2}/`
- CLI เดิม `extract-pdf-text` และ `extract-pdf-text-v1` ชี้ v1; ใช้ `extract-pdf-text-v2` สำหรับทดลอง v2
- ทำ improve ใน v2 ตามแนวคิดด้านล่างหลังตกลง behavior/สัญญา/schema ที่เกี่ยวข้อง ไม่ถือว่า Notes นี้เป็นอนุมัติเรียก provider หรือเปลี่ยน business behavior ทั้งหมดแล้ว
- สถานะทั้งสองชุดตอนแยก: pypdf extraction + quality check หน้าเปล่า/U+FFFD + unavailable fallback + atomic local PDF/JSON storage + stdout summary/file paths
- `unreadable_threshold_percent: 0` ไม่ได้บังคับ fallback: ถ้าไม่มี `�` และไม่ใช่หน้าเปล่า จะไม่เข้า fallback; v2 ตรวจ `C/M` แทรกคำไทยและติดธงได้เมื่อระบุ `suspicious_threshold_percent` ใน config JSON
- v1/การรัน v2 ที่ไม่เปิด detector คง schema 1; v2 ที่เปิด detector ใช้ schema 2 พร้อม `raw_text_quality` และ summary เพิ่ม ไม่ migrate/แก้ไฟล์ใน `backend/local-documents/` และไม่ copy เอกสารจริงเข้า tests

 ## Text-only LLM repair + OCR fallback

**สถานะ:** แนวคิดที่น่าสนใจสำหรับปรับปรุงในอนาคต ยังไม่ได้ implement หรืออนุมัติเปลี่ยน behavior/config/schema

### ปัญหาที่พบ

- PDF บางไฟล์แสดงภาษาไทยถูกต้อง แต่ Unicode mapping ของ font ไม่ครบ ทำให้ extract ได้ข้อความ เช่น `ทีC` หรือ `เชืMอ`
- Quality check ปัจจุบันตรวจหน้าเปล่าและสัดส่วน U+FFFD (`�`) จึงไม่จับข้อความผิดที่ยังเป็น Unicode ถูกต้อง
- การเปลี่ยน parser หรือโหลด font เพิ่มไม่ได้แก้ mapping ที่ขาดเสมอไป
- ต้องรองรับ PDF หลากหลาย จึงไม่ควรใช้การซ่อม font รายตัวหรือ replace ตัวอังกฤษทั้งเอกสารเป็นทางหลัก

### แนวทางที่น่าสนใจ

```text
Extract text → ตรวจช่วงน่าสงสัย
              ├─ มี text ใช้งานได้ → text-only LLM เสนอการแก้เฉพาะจุด → ตรวจข้อเสนอด้วยโค้ด
              └─ หน้าสแกน/text เสียหนัก → OCR → ตรวจคุณภาพอีกครั้ง
```

- ส่งเฉพาะช่วงน่าสงสัยพร้อมบริบทรอบข้างให้ LLM ไม่ส่งทุกหน้าโดยไม่จำเป็น
- ให้คืน structured patches: ตำแหน่งเริ่ม/จบ, ข้อความเดิม, ข้อความแก้ และเหตุผล ไม่เขียนทั้งหน้าใหม่
- กำหนดตำแหน่งเป็น Unicode code-point offsets อ้างอิง raw text ฉบับเดียวกัน แล้วตรวจข้อความเดิม/ขอบเขต/patch overlap ก่อนใช้
- ไม่ยอมรับการแก้นอกช่วงที่อนุญาต และตรวจการเปลี่ยนตัวเลขกับอังกฤษจริง เช่น `COVID-19`
- หากไม่มั่นใจหรือ validation ไม่ผ่าน ให้คงข้อความเดิม ไม่เติมข้อมูลเอง
- เก็บ `raw_text`, `corrected_text`, รายการแก้ และ model ที่ใช้แยกกัน ไม่ทับต้นฉบับ

### ข้อจำกัดและเรื่องที่ต้องตัดสินใจก่อนทำ

- Text-only LLM คาดเดาคำได้ แต่ไม่ยืนยันว่าตรงภาพ PDF ไม่สามารถกู้ข้อมูลที่ไม่มีใน text ได้อย่างน่าเชื่อถือ
- ฉบับแก้เป็นข้อเสนอที่ยังไม่ยืนยันกับต้นฉบับ โดยเฉพาะชื่อคน ตัวเลข และเอกสารกฎหมาย; guardrails ไม่รับประกันความถูกต้องทางความหมาย
- ต้องกำหนดเกณฑ์ตรวจช่วงน่าสงสัยโดยไม่ตีความว่าอังกฤษปนไทยผิดเสมอ รวมถึงนโยบาย review/ยอมรับฉบับแก้
- เลือก local model หรือ provider ที่อนุมัติ พร้อมข้อกำหนด privacy, ค่าใช้จ่าย, timeout และ failure semantics ก่อนส่งเอกสารจริงออกนอกเครื่อง
- หากทำจริง ต้องตกลง domain/port/outcome และ schema สำหรับ raw/corrected text กับ provenance ให้ชัดเจน; CLI summary และไฟล์ PDF ต้นฉบับควรคงเดิม
- ทดสอบผ่าน public boundaries ด้วยข้อความไทยปนอังกฤษที่ถูกต้อง, font mapping ที่ผิด, ตัวเลข/ชื่อเฉพาะ และข้อเสนอ LLM ที่ผิดขอบเขตหรือ malformed
- OCR เป็นอีกแนวทางสำหรับหน้าที่ไม่มี text ใช้งานได้ ไม่ใช่สิ่งที่ text-only repair ทดแทนได้ทั้งหมด

## Improve: detector คุณภาพข้อความไทยจาก PDF

**สถานะ:** ข้อ 1–3 เป็น integrated CLI feature ใน v2 แล้ว ตาม scope report-only ที่ยืนยัน; ไม่มี LLM/OCR

### Detector ที่ตกลงและต่อใช้งานแล้ว

- Owner เดิม `DocumentExtraction` ใน `v2/domain/documents/extraction.py`; local detector/projections อยู่ที่ `text_quality.py` ไม่สร้าง Entity/use case ซ้อน
- ตรวจ parser raw text เท่านั้น: Latin เดี่ยวชิดไทย (ใช้ Unicode categories/names ไม่ใช่ regex), Thai marks ไม่มีฐาน/ซ้ำ/หลายวรรณยุกต์บนฐานเดียว และ U+FFFD/control/private-use; ยังไม่ใช่ตัวตรวจการสะกด/ลำดับภาษาไทยครบทุกกรณี
- `suspicious_threshold_percent` แยกจาก unreadable threshold: นับ union ของตำแหน่งน่าสงสัยที่ไม่ใช่ whitespace ÷ จำนวน non-whitespace code points × 100; ติดธงเมื่อมากกว่า threshold เท่านั้น หน้าเปล่าได้สัดส่วน 0 แต่ยังใช้กฎ fallback เดิม
- ธงไม่แก้ข้อความ/status และไม่เรียก fallback เพิ่ม; `raw_text_quality` เก็บ raw source/spans/counts/threshold/flag แยกจาก terminal page text และอยู่ต่อหลัง fallback สำเร็จหรือล้มเหลว
- Interactor ส่ง document พร้อมรายงานเข้า store และส่ง semantic reports ผ่าน `ExtractionSaved` หลัง acknowledgement; LocalJsonExtractionStore เก็บรายงานจริงใน schema 2 ด้วย atomic publication เดิม
- เปิด detector ด้วย numeric `suspicious_threshold_percent` ที่ระบุใน `--config` เท่านั้น; ไม่ระบุ/`null` หมายถึงไม่ได้ประเมินและคง schema 1/summary เดิม ตัวอย่าง config ปัจจุบันตั้ง `0` ไว้แล้ว
- JsonCliPresenter เพิ่ม `summary.assessed_pages` และ `summary.suspicious_pages` เฉพาะเมื่อประเมินแล้ว ไม่ส่ง raw text/รายงานรายหน้าลง stdout
- Verification: v1/v2 unit + integration **302 passed**; PDF จำลอง, parser/store/CLI จริง, temporary Linux filesystem, failure/permissions/concurrency และการอยู่ร่วมของ schema 1/2 ผ่าน; compileall v2 ผ่าน
- ไม่รัน `คปภ.pdf` ซ้ำ ไม่เปลี่ยนเอกสารเดิม ไม่มี migration/deployment/provider calls; OCR/vision, LLM repair, font inspection และความแม่นยำเชิงความหมายยัง deferred/unverified

### แนวคิดที่เหลือ (ไม่ใช่ทั้งหมดที่ implement แล้ว)

1. **อังกฤษตัวเดียวติดอักษรไทย** — ใช้ regex lookaround ตรวจ Latin ตัวเดียวติดไทย โดยไม่จับส่วนหนึ่งของคำอังกฤษ/รหัส เช่น `COVID-19`, `B12`; นับรูปแบบที่เกิดซ้ำเพื่อเพิ่มความน่าสงสัย เช่น `ทีC`, `เชืMอ` แต่ต้องระวัง false positive อย่าง `วิตามินC`
2. **สระ/วรรณยุกต์ผิดตำแหน่ง** — สแกน Unicode code points/categories และใช้กฎลำดับอักษรไทย ตรวจ combining marks ที่ไม่มีพยัญชนะรองรับ อยู่หลังช่องว่าง หรือวรรณยุกต์ซ้ำผิดรูปแบบ เช่น `ผู้ป ่ วย`, `ก่้`; ช่องว่างกลางคำอย่าง `เปิ ด` ต้องอาศัยบริบท/พจนานุกรมเพิ่ม
3. **อักขระผิดปกติ** — ใช้ Unicode categories และรายการกฎตรวจ U+FFFD (`�`), control characters ที่ไม่ใช่ newline/tab ปกติ และ private-use characters; รายงานเป็นสัญญาณ ไม่ลบทิ้ง เพราะบางเอกสารอาจใช้อย่างถูกต้อง
4. **หลักฐานจาก font ใน PDF** — อ่าน encoding, `/ToUnicode` CMap และรหัส glyph ที่ใช้งานจริง เพื่อตรวจ mapping coverage ของ font แล้วเทียบกับข้อความน่าสงสัย; ต้องอ่าน PDF ต้นฉบับ ไม่ใช่ JSON อย่างเดียว และการไม่มี `/ToUnicode` ไม่ได้แปลว่า font เสียเสมอ

ผล detector ควรเก็บตำแหน่งเริ่ม/จบใน raw text, บริบท, เหตุผล, จำนวนครั้ง และระดับความน่าสงสัย โดยไม่อ้างเป็นเปอร์เซ็นต์ความถูกต้องหรือถือว่าเป็นคำผิดแน่นอน แยก quality assessment ออกจาก `unreadable_threshold_percent` ที่นับเฉพาะ `�`

แนะนำเริ่มข้อ 1–3 แบบ report-only แล้วเพิ่มข้อ 4 ภายหลัง ไม่บังคับ fallback อัตโนมัติจนกว่าจะตกลงนโยบายและจัดการกรณี fallback unavailable ซึ่งปัจจุบันทำให้ text ของหน้าที่ fallback ล้มเหลวเป็น `null`
