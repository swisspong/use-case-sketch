# แนวทางลดความล้มเหลวของ text repair: แบ่งชุด + checkpoint + resume

## สถานะและเป้าหมาย

ผู้ใช้เห็นด้วยให้บันทึกแนวทางนี้ไว้พัฒนาต่อ **ยังไม่ได้ implement หรืออนุมัติรายละเอียด contracts/schema/retry policy** เอกสารนี้ไม่ใช่อนุมัติให้เรียก provider เพิ่ม

เป้าหมายคือ **บางชุดล้มเหลวได้ แต่ผลที่สำเร็จไม่หาย และทำต่อเฉพาะส่วนที่ค้างได้** ไม่ใช่รับประกันว่าไม่มี error หรือข้อความที่ model เสนอถูกต้องแน่นอน

เริ่มจากแบ่งข้อความเป็นชุดเล็ก ๆ ใน application ก่อน ไม่จำเป็นต้องใช้ Provider Batch API ซึ่งช่วยจัดคิวงาน แต่ไม่ได้รับประกันว่าแต่ละรายการจะสำเร็จ

## หลักฐานจากการตรวจล่าสุด

- Request สังเคราะห์แบบข้อความและ JSON mode ได้ HTTP 200 และจบด้วย `stop`
- Request ของหน้าจริงใช้ prompt ประมาณ 20,000 tokens; budget 2048 และ 8192 ยังจบด้วย `length` และ JSON ไม่ครบ
- รอบ budget 8192 provider รายงาน completion 9373 tokens รวม reasoning 9047 tokens จึงยังยืนยันไม่ได้ว่า gateway บังคับ `max_tokens` ตาม semantics ที่คาด ห้ามถือว่า parameter นี้พิสูจน์เพดานค่าใช้จ่ายแล้ว
- ทั้งสองรอบที่ JSON ไม่ครบไม่มี repair record ใหม่ และ saved PDF/extraction ไม่เปลี่ยน
- เพิ่ม timeout/token อย่างเดียวจึงยังไม่ใช่วิธีแก้ที่พิสูจน์แล้ว ควรตรวจ parameter ลด reasoning ที่ gateway รองรับควบคู่กัน ไม่สุ่มใส่ parameter ของ provider อื่น

## Flow ที่เสนอ

```text
อ่าน immutable extraction snapshot + ตรวจสิทธิ์/eligibility
  → วางแผนชุดจาก suspicious spans และบริบท
  → บันทึก job/แผนชุดที่ผูกกับ snapshot
  → เรียก model ทีละชุดหรือพร้อมกันจำนวนน้อย
  → แปล offsets กลับต้นฉบับ + validate ด้วย domain จริง
  → checkpoint ผลและสถานะของแต่ละชุด
  → รวมข้อเสนอที่ไม่ขัดแย้ง + รายงาน completed/partial/failed

resume → ตรวจ snapshot/แผนเดิม → ทำเฉพาะชุดที่ยังไม่ terminal
```

### การแบ่งชุด

- รวม spans ที่ใกล้กันหรือมี context ซ้อนกัน; ส่งข้อความเฉพาะบริบทที่จำเป็น ไม่ส่งทั้งหน้าซ้ำทุกชุด
- จำกัดทั้งขนาด input และงบ output/reasoning; จำนวน spans อย่างเดียวไม่ควบคุม token budget
- ห้ามตัด suspicious span กลางช่วง; วางแผนให้ทุก span ถูกครอบคลุม และตรวจกรณีที่ span เดียวใหญ่เกินขนาดชุด
- ชุดแต่ละชุดมี identity และขอบเขต Unicode code-point offsets ที่แน่นอน อ้างอิง raw text ฉบับเดียวกัน
- หาก model ใช้ offsets ภายใน context ให้โค้ดแปลงกลับเป็น offsets ของหน้า และตรวจ bounds/การซ้อนทับ/การแตะ signal ด้วย domain จริง
- ตรวจ overlap/conflict ข้ามชุดด้วย ไม่ใช้ last-write-wins หรือเลือกข้อเสนอที่ขัดกันเองโดยไม่มีนโยบายที่ตกลง
- รักษา PDF, parser raw text และ extraction เดิม; ผลยังเป็นข้อเสนอ ไม่ใช่ accepted correction

### Checkpoint และ resume

- ผูก job กับ document/page, snapshot digest, chunk-plan version, prompt version และ approved preset/model; เก็บเฉพาะ provenance ที่จำเป็น ไม่เก็บ API key
- แยกสถานะการประมวลผลของชุดออกจากผลของ model:
  - processing: pending/running/succeeded/failed หรือชื่อที่ตกลงภายหลัง
  - model decision ที่ valid: suggested/no_changes/unrepairable
- Timeout, malformed JSON, `finish_reason: length` และ proposal ไม่ผ่าน validation **ไม่ใช่** no_changes/unrepairable
- บันทึก checkpoint แบบ atomic/durable ก่อน acknowledge ว่าชุดนั้นสำเร็จ; resume ต้องอ่านผลที่บันทึกแล้วได้จริง
- Resume ไม่เรียก model ซ้ำสำหรับชุดที่มี terminal checkpoint แล้ว; เมื่อ snapshot หรือแผนเปลี่ยน ให้หยุดหรือสร้าง job ใหม่ตามนโยบาย ไม่ reuse ผลเก่าเงียบ ๆ
- หน้าที่ยังมีชุดล้มเหลว/ค้างต้องแสดง partial/incomplete พร้อมจำนวนชุดที่ค้าง ไม่รายงานว่าทั้งหน้าสำเร็จ
- การ checkpoint ไม่รับประกัน exactly-once remote call: crash หลัง provider ตอบแต่ก่อนบันทึก หรือ timeout อาจทำให้ provider ทำงาน/คิดค่าใช้จ่ายแล้ว ต้องกำหนดการจัดการผลไม่แน่นอน

### Concurrency, retries และความปลอดภัย

- เริ่มจาก sequential หรือ concurrency ต่ำ แล้วกำหนดเพดานรวมให้ชัดเจน
- Retry เฉพาะ failures ที่นโยบายอนุญาต โดยจำกัด attempts, backoff และ cost/time budgets ไม่ retry ทุก error
- Authentication/config/model unsupported เป็นสิ่งที่ต้องแก้ ไม่ใช่เหตุให้ retry วน
- JSON ถูกตัด/ข้อเสนอผิดไม่ควรถูกส่งซ้ำด้วย request เดิมแบบไม่จำกัด; ต้องกำหนดว่าจะลดชุด/ปรับ budget/ส่งให้คนตรวจอย่างไร
- Timeout อาจมี remote effect แล้ว; retry อาจเสียค่าใช้จ่ายซ้ำ อย่าอ้าง provider idempotency จนกว่าจะยืนยันการรองรับ
- ต้องกำหนด claim/lease หรือ conditional publication หากหลาย worker/resume ทำ job เดียวกัน เพื่อไม่ให้เกิด competing checkpoints
- ใช้ private storage, safe error codes และ escape untrusted text ตามเดิม; keys มาจาก trusted JSON ตอน invocation เท่านั้น ไม่เข้า checkpoint/log/outcome

## ผลต่อ implementation เดิม

ยังอยู่ใน context `document_processing/v2` และ domain owner `documents`; ไม่เพิ่ม bounded context หรือ competing extraction write model เพียงเพราะมี batch

ปัจจุบัน `repair_extracted_text` ส่ง raw text ทั้งหน้าและทุก spans ใน **หนึ่ง invocation** แล้วบันทึกเฉพาะ completed outcome ผ่าน append-only `RepairRunRepository`

แนวทางใหม่จึงต้องตกลงก่อนเปลี่ยน:

- `TextRepairer` input/guarantees จาก whole-page invocation เป็น chunk invocation พร้อม translation responsibility
- Interactor ที่แสดงการวางแผน/ประมวลผล/validate/checkpoint/รวมผลอย่างชัดเจน ไม่ซ่อน workflow ทั้งหมดใน adapter
- Ownership ของ chunk plan และ job transitions; reuse `PageRepairSuggestions` สำหรับ invariants เดิม และเพิ่มการตรวจข้อเสนอข้ามชุดตามกฎที่ยืนยัน
- Persistence contract สำหรับ job/checkpoints: repository เดิมยังไม่มี write path สำหรับ pending/failed/partial job อย่ายัดข้อมูลเหล่านี้เป็น completed repair record
- Output Boundary/Presenter/CLI สำหรับ partial progress, resume และ exit codes; ไม่ทำลาย consumers/schema เดิมเงียบ ๆ

## เรื่องที่ยังต้องตัดสินใจ

1. ขนาด input/context, chunk planning และการจัดการ span ใหญ่/ข้อเสนอข้าม context
2. Job identity, source binding, terminal statuses, conflict resolution และความหมายของ completed เมื่อบางชุด unrepairable
3. Manual/automatic retry, max attempts, concurrency, cost limits และผลที่ remote execution ไม่แน่นอน
4. รูปแบบ checkpoint/schema และ compatibility ของ repair history เดิม
5. Gateway/model รองรับ reasoning/token controls อะไรจริง

## หลักฐานทดสอบที่ต้องมีเมื่อ implement

- ชุดเล็กสำเร็จหลายชุด, บางชุดล้มเหลวโดยไม่สูญเสียผลสำเร็จ และ resume เฉพาะชุดที่ค้าง
- Exact document/page/context/model/key arguments และ offsets ที่แปลงกลับต้นฉบับ; ครอบคลุมทุก signal โดยไม่ส่งข้อความผิดหน้า
- Partial JSON, length, bad offsets, overlap/conflict และ dependency failures ไม่กลายเป็น false success
- Snapshot เปลี่ยน, checkpoint write/ack failure, crash window และ concurrent workers/resume ตาม consistency contract ที่เลือก
- Real checkpoint adapter tests บน isolated filesystem/DB ที่ใช้จริง; unit mocks ไม่พิสูจน์ atomicity/durability
- Regression ของ extraction/repair เดิมและ safe presentation; live provider tests ต้องได้รับอนุมัติแยก ไม่มีการรับประกัน semantic correctness จาก HTTP 200 หรือ schema-valid JSON
