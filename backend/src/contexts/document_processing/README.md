# Document processing versions

- **[v1](v1/):** preserved baseline. Existing `extract-pdf-text` and explicit
  `extract-pdf-text-v1` console commands point here.
- **[v2](v2/):** independent working copy with an opt-in report-only detector.
  Use `extract-pdf-text-v2` and set `suspicious_threshold_percent` in its trusted
  config to enable raw reports, JSON schema 2 and additional summary counts.
- **[v3](v3/):** extraction + OCR-suggestion working version (text repair and
  vision fallback removed). Use `extract-pdf-text-v3` (no `--preset`). Pages that
  are blank or whose problem characters (U+FFFD + font-substitution/Thai-mark/
  split-syllable signals) exceed `unreadable_threshold_percent` are saved with
  `ocr_suggested: true` in JSON schema 3; no model is called. The separate,
  user-triggered `ocr-document-pages-v3` command OCRs saved pages and appends
  attempts under `ocr/`. v1/v2 and saved data are preserved.

Each version retains `application/use_cases/extract_pdf_text/`, `domain/documents/`,
`infrastructure/`, `presentation/` and its own `composition.py`. Relative imports
stay within the owning version; do not import implementation code across versions.
Existing v1/v2 code and commands are preserved. See the
[v3 run instructions](../../../README.md#run-v3) for installation and CLI examples.

## v2 shared JSON configuration

`backend/examples/document_processing_config.json` replaces the extraction-only
example name and serves both v2 use cases. `v2/application/model_presets.py` owns
the shared catalogue: every trusted preset must have a nonblank string `api_key`,
even offline. Missing/invalid keys fail before I/O with configuration exceptions.
Interactors pass only the selected preset/key to model ports; keys are hidden from
repr and never enter domain state, persistence or Output Boundary outcomes.
Extraction/repair domain ownership and flat use-case layout remain unchanged.

Repair wiring/client uses only the selected `preset.api_key` from JSON, without
an environment lookup or separate composition/adapter key. Both CLIs use the same
strict private JSON loader: owner-only regular file, no final symlinks/duplicate
keys/nonfinite numbers, bounded to 16 MiB; parent paths must be trusted.
Integration tests verify exact Authorization, safe failures, no key in stored or
presented data, and chained extraction/repair with a shared private catalogue.
Vision fallback remains offline. Use a chmod-600 `examples/*.local.json` copy
(gitignored) for real keys; tracked example keys are placeholders.
v1 stays unchanged; use its original key-free configuration schema separately.

## v3 runtime

```text
extract-pdf-text-v3
└─ ExtractPdfTextInputBoundary → ExtractPdfTextInteractor → DocumentExtraction
   ├─ PypdfTextExtractor → original PDF bytes
   ├─ LocalJsonExtractionStore → exact PDF + pages with OCR suggestion (schema 3)
   │                            + optional raw reports, atomic local publication
   └─ JsonCliPresenter → total_pages, ocr_suggested_pages, optional report counts
```

```text
ocr-document-pages-v3 (presentation/ocr_document_pages_cli.py, trusted OS-user CLI)
└─ OcrDocumentPagesInputBoundary → OcrDocumentPagesInteractor → OcrAttempt
   ├─ LocalJsonSavedDocumentSource → <id>/original.pdf + extraction.json (schema 3)
   ├─ Pypdfium2PageRenderer → one PNG per page, bounded size
   ├─ OpenAICompatibleOcrReader → POST <endpoint>/chat/completions, selected preset key
   ├─ LocalJsonOcrAttemptStore → <id>/ocr/<attempt_id>.json, atomic append-only
   └─ JsonOcrCliPresenter → per-status page numbers + attempt path (no OCR text)
System failures → safe stderr JSON / exit 1, no retry
build_local_ocr supplies per-execution adapters; the CLI creates the Presenter
```

Provider compatibility (real LiteLLM/model vision support and JSON mode) is
verified only against a synthetic loopback server, not a live endpoint.

## v1/v2 runtime

```text
Version-specific CLI controller
└─ ExtractPdfTextInputBoundary → ExtractPdfTextInteractor → DocumentExtraction
   ├─ PypdfTextExtractor → original PDF bytes
   ├─ UnavailableFallbackExtractor → fallback_unavailable
   ├─ LocalJsonExtractionStore → exact PDF + terminal pages + optional v2/v3 raw reports
   │                            atomic local publication, schema 1/2
   └─ ExtractPdfTextOutputBoundary → JsonCliPresenter → summary/counts/absolute paths
System failures → safe stderr JSON / exit 1, no automatic retry
```

The domain checks blank pages and U+FFFD ratio strictly greater than the original
unreadable threshold. Threshold zero is not force-fallback. v2/v3 additionally detect
suspicious raw text using local Latin/Thai-mark/unusual-character heuristics when
`suspicious_threshold_percent` is configured. It flags strictly above that separate
threshold without changing text/status or requesting fallback; raw reports survive
existing fallback transitions. Missing/null config means not assessed. Rendering,
OCR/vision, font inspection and force-fallback remain deferred. v2 text-only repair
is a separate opt-in command, never an automatic extraction transition. v3 has no
text-repair operation or fallback; see the v3 runtime above.

### v2 repair only (removed from v3)

```text
repair-extracted-text-v2 / repair_extracted_text_cli.main (trusted OS-user CLI)
└─ RepairExtractedTextInputBoundary → RepairExtractedTextInteractor
   ├─ RepairSourceText / PageRepairSuggestions
   ├─ LocalJsonRepairPageSource → coherent saved schema 1/2 snapshot
   ├─ OpenAICompatibleTextRepairer → one Chat Completions request, selected JSON API key
   ├─ LocalJsonRepairRunRepository → append-only repair-runs/<id>/record.json
   └─ RepairExtractedTextOutputBoundary → JsonRepairCliPresenter → summary/identity/path
System failures → safe stderr JSON / exit 1; no automatic retry
build_local_text_repair supplies per-execution dependencies/Presenter
```

Only validated model outcomes are appended before presentation, not rejections or
invalid proposals. Existing extraction/PDF files never change. Repair records have
an independent schema version 1. Real provider capability/compatibility, semantic
repair accuracy and multi-user IAM are not established by local tests. See the
[CLI/storage documentation](../../../README.md#v2-text-only-repair-and-json-repository)
for settings, storage assumptions and uncertain/post-commit failure handling.

## Next session

1. Read [CLI/storage documentation](../../../README.md), including the v3 run instructions.
2. Confirm the selected improvement and its behavior before changing contracts,
   quality policy, configuration or persisted schema. Notes are proposals, not
   authorization for remote document uploads or blanket business changes.
3. Change only v3 source and its owning tests for new improvements. Run v1/v2
   regression as baselines; fixes are not automatically shared between copies.
4. Keep stdout summary-only, preserve sensitive source PDFs, and do not copy
   `local-documents` or private documents into any source tree or committed tests.

Tests are under `backend/tests/{unit,integration}/contexts/document_processing/v1/`
and `v2/`, `v3/`. From the repository root, after installing the editable backend package:

```sh
cd backend
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v1 \
  tests/integration/contexts/document_processing/v1 -q
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v2 \
  tests/integration/contexts/document_processing/v2 -q
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v3 \
  tests/integration/contexts/document_processing/v3 -q
```

v1 and unassessed v2 runs keep the existing schema 1/summary. Assessed v2 runs
store schema 2 with `raw_text_quality` and summarize assessed/suspicious page counts.
v3 always stores schema 3 with per-page OCR suggestions.
Schema version is not application version. Existing documents are never migrated
or overwritten. v1/v2 vision fallback remains offline. v2 alone retains explicit
text-only repair; v3 tests cover extraction and user-triggered OCR (synthetic
loopback provider).
