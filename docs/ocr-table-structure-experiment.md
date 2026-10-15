# OCR table structure: experiment log (2026-10-16)

Why `adapters/openai_ocr.py` uses two passes (plain transcription, then layout-only
structuring) instead of one prompt that returns tables.

## Setup

- Document `73700e9a-ff91-436c-9e64-4e55c3902aa6`, 1 page: a scanned meeting summary
  (หน้า ๔๑, สรุปมติ กนช. ครั้งที่ ๕/๒๕๖๘). `image_percent` = 100.
- Nested layout:
  - **Layout frame:** a page-wide 3-column grid
    (วาระที่ | มติที่ประชุม/ข้อสั่งการ | หน่วยงานที่รับผิดชอบ). Its cells hold paragraphs,
    and the first row continues from the previous page, so it has no agenda number.
  - **Data table:** "ผลการวิเคราะห์เชิงเศรษฐศาสตร์ | ปี ๒๕๖๘" (8 rows), inside the
    resolution cell of agenda ๔.๘.๔.
- Preset `mfec-gemini`, model `gemini-3.8-flash`, through the OpenAI-compatible
  endpoint. The page was rendered by the production renderer (longest side 2000 px)
  unless noted otherwise.
- Ground truth was checked by eye against the rendered page at 6× zoom, for example
  ๗๒.๙๐, not ๓๒.๙๐.

## Before: parser vs current OCR

The text layer that the parser extracted has 6 wrong values. The stored OCR, from the
old single prompt with "No markdown", has none, but it has no table structure.

| Spot | PDF | Parser | OCR (old prompt) |
|---|---|---|---|
| Flood year | ปี ๒๕๔๖ | ๒๕๕๖ ❌ | ✅ |
| Damaged area | ๒๐๐,๐๐๐ ไร่ | ๒,๐๐๐ ❌ | ✅ |
| New canal | คลองขุดใหม่ | คลองชุดใหม่ ❌ | ✅ |
| Total length | ๓๘.๘๕๒ กม. | ๓๘,๘๕๒ ❌ | ✅ |
| ลำห้วยยาง flow | ๒๐๐ CMS | `๒๐o CMs` ❌ | ✅ |
| D๑ flow | ๓๕๐ CMS | ๕๐ CMS ❌ | ✅ |

## Runs

Checkpoints are the spots where at least one run was wrong. **Table** means a valid pipe
table with a header and a separator row. **Frame** means the layout frame is written as
labelled blocks (`วาระที่:` / `มติที่ประชุม/ข้อสั่งการ:`), not as pipes.

| # | Variant | Runs | Structure | ท่าไม้รวก | ๗๒.๙๐ | Other checkpoints¹ |
|---|---|---|---|---|---|---|
| 1 | Old prompt ("No markdown") | 4 | none | 4/4 | 4/4 | 4/4 |
| 2 | Prompt A: tables + frame-as-blocks, short rules | 2 | 1 ok; 1 broken (frame drawn as pipes, data table inside a cell joined with `<br>`) | 2/2 | 2/2 | 2/2 |
| 3 | Prompt B: stricter numbered rules, "never use `<br>`" | 3 | 3/3 ok | 2/3 (→ ท่ายาง) | 2/3 (→ ๓๒.๙๐) | 3/3 |
| 4 | Prompt B, `temperature=0` | 3 | 2/3 (one run lost the separator row) | **0/3** | 1/3 | 3/3 |
| 5 | Prompt B, 3000 px image | 3 | 3/3 ok | 3/3 | **0/3** | 3/3 |
| 6 | Two-pass (scratch script) | 3 | 3/3 ok | 3/3 | 3/3 | 3/3 |
| 7 | Two-pass (final adapter, 3 parallel runs, 60 s deadline) | 3 | 2/3; 1 fell back to plain text (deadline hit in pass 2) | 3/3 | 3/3 | 3/3 |
| 8 | Two-pass (final adapter, sequential, 180 s deadline) | 2 | 2/2 ok | 1/2² | 2/2 | 2/2 |

¹ ปี ๒๕๔๖, ๒๐๐,๐๐๐ ไร่, คลองขุดใหม่, ๓๘.๘๕๒, ๒๐๐ CMS, D๑ ๓๕๐ CMS.
² Pass 1 (plain transcription) read ท่ายาง, and pass 2 copied it faithfully. If pass 2
had changed the word itself, the content check would have rejected it (see below). The
two passes do not fix pass-1 misreads. They avoid adding new ones.

### Findings

- The old prompt dropped tables because it said "No markdown". The model can read the
  page.
- When one call has to both read the page and lay out tables, digits and names get
  misread: ๗→๓ in 6 of 12 runs in rows 3 to 5, and ท่าไม้รวก→ท่ายาง (a nearby word) in
  4 of 12. `temperature=0` and a higher resolution did not fix this. Each fixed one
  error and made the other worse.
- With separate passes, digits stay correct (8/8 runs from rows 6 to 8), and the
  structure is correct in every run that finished.

## Implementation

`app/modules/documents/adapters/openai_ocr.py`

1. **Pass 1:** the old plain-transcription `PROMPT`, unchanged.
2. **Pass 2:** `LAYOUT_PROMPT` with the transcription and the same image: "copy every word
   and number exactly; use the image only for structure". Layout frames become labelled
   blocks, data tables become pipe tables, and HTML or nested tables are not allowed.
3. **Guard:** `rules.same_content(plain, structured)` keeps pass 2 only if no character is
   added or substituted, and every pass-1 line is still present. The one exception is a
   short run of frame-header lines that became labels. Whitespace, pipes and separator
   rows are ignored. If the check fails, or pass 2 errors, truncates or misses the
   deadline, the result is the pass-1 text. A pass-1 failure is reported as before
   (`provider_timeout` | `provider_error` | `invalid_output`).
4. **Deadline:** both passes share one deadline, `DOCUMENTS_OCR_TIMEOUT_SECONDS`.

The guard was checked against the real outputs above:

| Input to `same_content` | Result |
|---|---|
| Rows 6 runs 1 to 3 (correct re-layout, header row dropped, footer reordered) | accepted 3/3 |
| Same runs with ๗๒.๙๐→๓๒.๙๐, ท่าไม้รวก→ท่ายาง, a content line dropped, or `<br>` added | rejected (all) |
| 8 single-pass outputs from rows 2 to 5 compared with a pass-1 transcription | accepted only the 2 with every checkpoint right; rejected the other 6 |

Tests: `tests/documents/test_ocr_structure.py` (rule, no DB) and
`tests/documents/test_ocr_page.py::test_ocr_adapter_structures_tables_only_when_text_is_unchanged`
(adapter, `httpx.MockTransport`). `pytest -q`: 162 passed. `lint-imports`: 3 kept.
Playwright e2e: 81 passed, with no change to the e2e suite.

## Open issues

- **Latency (resolved):** pass 1 takes about 20 s and pass 2 about 37 s, about 58 s in
  total. With the old 60 s deadline, pass 2 often ran out of time and the plain text
  was returned (row 7). `DOCUMENTS_OCR_TIMEOUT_SECONDS` is now 90 by default, and the
  frontend waits 130 s for `POST /documents/{id}/ocr` (90 s OCR + up to 30 s render +
  save).
- **Quality metrics** are computed on the returned text, so pipes and labels count as
  characters: `thai_percent` was 92.57 instead of 93.94, and `text_chars` was 2531
  instead of 2492.
- **UI** shows the text with `whitespace-pre-wrap`, so pipe tables appear as raw text.
- Only one page was tested. Pages without tables, with several tables, or made only of a
  table are not covered yet.

## Experiment 2: image input (resolution vs PDF), 2026-10-16

Question: does higher resolution, or sending the original PDF, make OCR more accurate?

### Provider facts (preset `mfec gemini`: LiteLLM → Vertex, `gemini-3.8-flash`)

Image tokens are fixed per image, whatever the PNG size. The provider resizes images
itself:

| Input | `image_tokens` |
|---|---|
| PNG 1000 / 2000 / 3500 px (default) | 1092 / 1092 / 1092 |
| PNG, `image_url.detail: "low"` | 266 |
| PNG, `image_url.detail: "high"` (= default) | 1092 |
| PNG, `image_url.detail: "ultra_high"` | 2184 |
| PDF (`file` part or `image_url` with `application/pdf`) | 532 |

- A larger PNG does not help by itself. Only `detail: "ultra_high"` doubles what the
  model sees.
- A PDF is rasterised by the provider at a lower budget than our PNG. `text_tokens`
  only counted our prompt, so no text layer reached the model.
- Native scan resolution: the table page is 1650×2330 (200 dpi). The superscript page
  is 2483×3508 (300 dpi, JBIG2). Our renderer sends at most 2000 px (≈171 dpi).

### Variants

All variants use the same two passes, prompts and `same_content` guard as the adapter. 3
runs per variant per page, 6 requests in parallel.

- **base:** production renderer, PNG 2000 px, default detail.
- **zoom:** PNG at native scan size, with `detail: "ultra_high"`.
- **pdf:** the original PDF as a `file` part.

### Checkpoints (verified by eye on the scans)

- **Table page (8):** the 8 spots from experiment 1.
- **Superscript page (13):**
  - page number `- ๓ -`, `๒.๒.๑.๓`, `๒.๒.๓.๑`
  - ปรมาณูเพื่อสันติ, ปกติทุกราย, `(๑) โรงพยาบาลส่งเสริม…`, `[ซิลิโคซิส` (square
    bracket)
  - ๔,๙๔๖, ๒,๕๔๓, พ.ศ. ๒๕๖๒
  - superscript ๓ after `(โรคจากรังสีแตกตัว)`, superscript ๔ after `ซีเซียม-๑๓๗`, and
    footnote marker ๔

Baselines: the superscript page parser scores 4/13 and the table page parser scores 2/8.

### Results

| Variant | Image tokens | Checkpoints right | Errors | Pass 1 ignored "No markdown" (`<br>` tables) | Final has clean structure | Pass 1 avg | Total avg (max) |
|---|---|---|---|---|---|---|---|
| base | 1092 | 62/63 | ๔,๙๔๖→๔,๙๔๐ (1 run) | 0/6 | 6/6 | 19.5 s | 47.7 s (74.7 s) |
| zoom | 2184 | 63/63 | none | 2/6 (table page) | 3/5¹ | 13.4 s | 42.6 s (59.2 s)¹ |
| pdf | 532 | 62/63 | ๒๕๔๖→๒๕๕๖ (1 run)² | 4/6 | 2/6 | 11.2 s | 40.1 s (50.2 s) |

¹ One zoom run lost pass 2 to an HTTP 429 (rate limit from parallel requests). It is
excluded from the structure and time columns, and its pass-1 text is scored.
² This is the same wrong year as the PDF's own text layer (the parser's error). The usage
data shows no text layer was sent, so the cause is unproven.

### Findings

- Accuracy is about the same for all three, within 1 checkpoint out of 63. On these two
  pages, resolution is not what limits accuracy, and 2000 px with the default detail is
  enough.
- With zoom and pdf, pass 1 often skips its reasoning (`reasoning_tokens` absent) and
  ignores "No markdown". It returns pipe tables with `<br>` cells. The guard then
  rejects pass 2, because pass-1 lines are missing, so the final text is pass 1's
  broken markup. This never happened with base.
- pdf sends the least detail, and it gave the fewest clean structures (2/6).
- zoom costs twice the image tokens. It found no error that base missed reliably (base
  missed 1 checkpoint in 1 of 6 runs).

### Decision

Keep base: PNG 2000 px with the default detail. Revisit `detail: "ultra_high"` only if
pages with very small print fail.

Follow-up: if pass 1 returns markup (`|` rows or `<br>`), the fallback still returns
that markup. This happened in 0/6 runs with base, but the guard could also handle it.

## Experiment 3: guard against pass-1 markup, 2026-10-16

Change: `rules.strip_markup` flattens what pass 1 returns despite "No markdown". `<br>`
becomes a line break, simple inline tags (`sup`, `b`, …) are removed and their text
kept, and each pipe-table cell becomes its own line without separator cells. Text without
markup is returned byte-for-byte. The adapter applies it before pass 2, so both the
structuring input and the fallback are plain.

Offline, on the 6 experiment-2 runs whose pass 1 had markup: no `<br>`, `|` or `---` was
left, every checkpoint was unchanged, and `same_content` accepted all 6 recorded pass-2
outputs. All earlier clean pass-1 texts and the parser text came back unchanged.

Live, on the table page with the variants that triggered markup (3 pdf and 3 zoom runs,
2 at a time):

| Run | Pass 1 had markup | Pass 2 | Final | Checkpoints |
|---|---|---|---|---|
| pdf 1 | yes | cut off (`finish_reason=length`) | flattened pass 1, clean | 8/8 |
| pdf 2 | yes | accepted | structured | 7/8 (๒๕๔๖→๒๕๕๖ in pass 1) |
| pdf 3 | no | accepted | structured | 8/8 |
| zoom 1 | no | cut off (`finish_reason=length`) | pass 1, clean | 8/8 |
| zoom 2 | no | accepted | structured | 8/8 |
| zoom 3 | yes | accepted | structured | 8/8 |

- The final text never contained `<br>` or broken pipe rows (0/6, compared with 6/12 in
  experiment 2 for pdf and zoom).
- New finding: pass 2 can run out of `max_tokens` (8192) on reasoning. In both cut-off
  runs it spent about 7,860 reasoning tokens and only about 330 on output. Restructuring
  needs no deep reasoning, so pass 2 could use a low reasoning effort or a larger
  `max_tokens`. That would likely also cut its ~25–40 s latency (not yet tested).
- pdf input misread ๒๕๔๖ as ๒๕๕๖ again (2 of 6 pdf runs overall). base never did.

## Experiment 4: pass 2 with `reasoning_effort: "low"`, 2026-10-16

The proxy accepts `reasoning_effort`. Single pass-2 probe on the same recorded
transcription:

| Effort | Pass 2 time | Reasoning tokens | Output tokens | Pipe rows |
|---|---|---|---|---|
| default | 29.1 s | 3023 | 4171 | 9 |
| none | 18.8 s | — | 1142 | 8 (separator missing) |
| minimal | 21.5 s | — | 1148 | 9 |
| low | 28.3 s | — | 1142 | 8 (separator missing) |
| medium | 37.4 s | 3607 | 4755 | 9 |

Production input (base: PNG 2000 px), pass 1 unchanged, pass 2 with `low`, 3 runs per
page, 2 at a time. It is compared with the experiment-2 base runs (default effort):

| | Default effort | Pass 2 `low` |
|---|---|---|
| Pass 2 time | 22.1–45.7 s | **6.5–11.5 s** |
| Total time | 36.7–74.7 s (avg 47.7) | **17.3–30.8 s (avg 25.0)** |
| Pass 2 reasoning tokens | 2689–4060 | none |
| Pass 2 accepted by the guard | 6/6 | 5/6¹ |
| Data tables well formed (header + separator, equal columns) | 3/3 | **1/2**² |
| Checkpoints | 62/63 | 62/63 (๔,๙๔๖→๔,๙๔๐ again, pass 1) |

¹ The rejected run is a pass-1 problem, not pass 2: pass 1 returned an HTML `<table>`.
`strip_markup` now also flattens HTML table tags (`table`, `tr`, `td`, `th`, …, with
attributes), and drops blank lines in markup mode. Re-checked offline, that run's pass 2
would be accepted. All 10 recorded pass-1 outputs with markup flatten cleanly, with
checkpoints unchanged.
² Without reasoning, pass 2 sometimes omits the `| --- |` separator row (1 of 2 table
runs and 2 of 3 non-reasoning probes). The text is unchanged, so the guard accepts it, but
the result is not a valid Markdown table.

### Findings

- `low` halves the total time, and pass 2 no longer risks running out of `max_tokens` on
  reasoning (experiment 3).
- Structure quality drops: separator rows go missing. Adopting `low` needs a
  deterministic repair (insert the separator row after a table's first row), or a guard
  that rejects malformed tables. `minimal` kept the separator in 1/1 probe, which is too
  few to rely on.

## Experiment 5: final adapter (pass 2 `low` + `repair_tables`), 2026-10-16

Change: pass 2 sends `reasoning_effort: "low"`, and `rules.repair_tables` inserts a
missing separator row after a pipe table's header. Cell text is never touched. Offline,
the repair fixed the one malformed experiment-4 table and left the 19 other accepted
outputs byte-identical.

Live, with the production `OpenAIOcrReader` and its 90 s deadline, 2 runs at a time:

| Run | Pass 1 | Pass 2 (`low`) | Total | Structure | Tables well formed | Checkpoints |
|---|---|---|---|---|---|---|
| table 1 | 18.0 s | 11.7 s | 29.7 s | yes | 1/1 | 8/8 |
| table 2 | 30.4 s | 10.8 s | 41.2 s | yes | 1/1 | 8/8 |
| super 1 | 14.1 s | 7.3 s | 21.4 s | yes (labelled frame) | — | 13/13 |
| super 2 | 13.4 s | 9.8 s | 23.3 s | yes (labelled frame) | — | 13/13 |

Round 3 could not run. The preset's API key hit its spending cap (`429 budget_exceeded`,
$5.00). Until the budget is raised, every OCR request returns `provider_error`.

Note: a provider that does not support `reasoning_effort` and rejects it would fail pass
2 every time. OCR would still return plain text, but with no tables. The LiteLLM →
Vertex Gemini preset accepts it.
