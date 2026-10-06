# Document processing versions

- **[v1](v1/):** preserved baseline. Existing `extract-pdf-text` and explicit
  `extract-pdf-text-v1` console commands point here.
- **[v2](v2/):** independent working copy with an opt-in report-only detector.
  Use `extract-pdf-text-v2` and set `suspicious_threshold_percent` in its trusted
  config to enable raw reports, JSON schema 2 and additional summary counts.

Each version retains `application/use_cases/extract_pdf_text/`, `domain/documents/`,
`infrastructure/`, `presentation/` and its own `composition.py`. Relative imports
stay within the owning version; do not import v1 code from v2 or vice versa.

## Current runtime

```text
Version-specific CLI controller
└─ ExtractPdfTextInteractor → DocumentExtraction
   ├─ PypdfTextExtractor → original PDF bytes
   ├─ UnavailableFallbackExtractor → fallback_unavailable
   ├─ LocalJsonExtractionStore → exact PDF + terminal pages + optional v2 raw reports
   │                            atomic local publication, schema 1/2
   └─ JsonCliPresenter → summary/counts/absolute file paths, no document text on stdout
System failures → safe stderr JSON / exit 1, no automatic retry
```

The domain checks blank pages and U+FFFD ratio strictly greater than the original
unreadable threshold. Threshold zero is not force-fallback. v2 additionally detects
suspicious raw text using local Latin/Thai-mark/unusual-character heuristics when
`suspicious_threshold_percent` is configured. It flags strictly above that separate
threshold without changing text/status or requesting fallback; raw reports survive
existing fallback transitions. Missing/null config means not assessed. Actual
rendering, OCR/vision, LLM repair, font inspection and force-fallback remain deferred.

## Next session

1. Read [improvement notes](../../../NOTES.md) and [CLI/storage documentation](../../../README.md).
2. Confirm the selected improvement and its behavior before changing contracts,
   quality policy, configuration or persisted schema. Notes are proposals, not
   authorization for remote document uploads or blanket business changes.
3. Change only v2 source and its owning tests for new improvements. Run v1
   regression as the baseline; fixes are not automatically shared between copies.
4. Keep stdout summary-only, preserve sensitive source PDFs, and do not copy
   `local-documents` or private documents into either source tree or committed tests.

Tests are under `backend/tests/{unit,integration}/contexts/document_processing/v1/`
and `v2/`. From the repository root, after installing the editable backend package:

```sh
cd backend
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v1 \
  tests/integration/contexts/document_processing/v1 -q
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v2 \
  tests/integration/contexts/document_processing/v2 -q
```

v1 and unassessed v2 runs keep the existing schema 1/summary. Assessed v2 runs
store schema 2 with `raw_text_quality` and summarize assessed/suspicious page counts.
Schema version is not application version. Existing documents are never migrated
or overwritten, and no production OCR/LLM capabilities have been added.
