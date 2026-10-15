# Documents: OCR one page and compare with the parser

Based on Penpot `Document detail` (`OCR running (sync)`, `OCR compare`, `Tab ผลเดิม`,
`Tab OCR`, `OCR quality failed`, `Detail states`, `Detail states · Additional`, OCR
behavior annotations) and `API spec / Document detail` boards 01, 02, 12, 13 and 90.

## API

`POST /documents/{id}/ocr` with `{ "page": n, "preset_id": uuid | null }` (slice
`app/modules/documents/ocr_page.py`). The request is synchronous and handles one page.

- Checks run before any rendering or provider call: DOC_007 (missing document), DOC_009
  (page outside 1..page_count), DOC_008 (document stored before page assessment),
  DOC_012 (no preset_id and no default) and DOC_013 (unknown preset_id). A malformed
  body or a non-integer page returns REQ_001.
- Flow: read the document and snapshot (tx) → resolve the preset (short tx) → render the
  page and call the provider (no tx) → save (tx).
- `200 {status: "ok", ocr, text_passed}` replaces the previous OCR result.
  `200 {status: "failed", reason}` (provider_timeout | provider_error | invalid_output)
  saves nothing, so the previous result is kept. Failures are not recorded.
- OCR quality uses the upload-time threshold snapshot and the parser's image coverage.
  Only the text changes. Historical minimum-Thai snapshots keep their direction.
- `GET …/pages/{n}` returns `ocr` (latest success or null).
- `PageSummary.has_ocr = ocr != null`.
- `text_passed = parser passed || OCR passed`.
- `ocr_suggested` and `ocr_suggested_count` keep their parser-only meaning.

Storage: nullable JSONB `document_pages.ocr` (migration `20261016_page_ocr`).

## Adapters and wiring

- `adapters/page_renderer.py`: PDFium (pypdfium2) in a killable subprocess, 200 dpi, longest
  side ≤ 2000 px, deadline `DOCUMENTS_PARSE_TIMEOUT_SECONDS`. Failure → 500 SYS_002.
- `adapters/openai_ocr.py`: two Chat Completions requests with the page as a PNG data URL,
  sharing the total deadline `DOCUMENTS_OCR_TIMEOUT_SECONDS` (90; the frontend waits 130 s). Pass 1 transcribes
  plain text. Pass 2 restructures that text into Markdown pipe tables and labelled
  layout-frame blocks. It is kept only when `rules.same_content` confirms the text is
  unchanged; otherwise pass 1 is returned. Pass 2 uses `reasoning_effort: "low"`, and
  a missing table separator row is repaired; markup in pass 1 is flattened first
  (see `docs/ocr-table-structure-experiment.md`). No automatic retries, because the user
  retries explicitly. A truncated reply (`finish_reason=length`) or a malformed reply in
  pass 1 is `invalid_output`. Credentials and provider text are never logged.
- Presets come from `llm_config/credentials.py` (a public read-only lookup that decrypts the
  key). `shared/deps.py` adapts it to the documents `OcrPresets` port, so the modules stay
  independent.

## UI (`frontend/src/features/documents/page-results.tsx`)

- **Parser not passed:** shows the alert with the button “OCR หน้านี้”.
- **Parser passed:** shows a plain button “OCR หน้านี้”.
- **After clicking OCR:** shows “กำลังเตรียม OCR…” while `GET /llm/presets` loads, then
  resolves the default preset and POSTs it with its id.
- **While running:** shows “กำลัง OCR หน้า n ด้วย {preset}…” with elapsed time and a
  beforeunload warning. OCR buttons are disabled on every page.
- **Rerunning:** keeps the previous Compare view with its text and metadata.
- **On success:** the response updates the panel and the thumbnail colour without a
  refetch. Tabs: เทียบผล / ผลเดิม / OCR.
- **Errors:** follow the Penpot copy for each state. Every retry is user-initiated.
- **DOC_012:** links to `/settings?tab=llm`, which opens the LLM tab.

## Verification

- `tests/documents/test_ocr_page.py` (real Postgres): handler rules, no transaction open
  during the provider call, endpoint mapping, the credential lookup, the adapter
  (MockTransport) and real PNG rendering.
- `frontend/e2e/document-ocr.spec.ts`: browser journeys (see `frontend/e2e/README.md`).
- Not covered: a real vision provider. Provider compatibility (vision input support) is a
  manual check with real credentials.
