# Document processing versions

- **[v1](v1/):** preserved baseline. Existing `extract-pdf-text` and explicit
  `extract-pdf-text-v1` console commands point here.
- **[v2](v2/):** independent working copy with an opt-in report-only detector.
  Use `extract-pdf-text-v2` and set `suspicious_threshold_percent` in its trusted
  config to enable raw reports, JSON schema 2 and additional summary counts.

Each version retains `application/use_cases/extract_pdf_text/`, `domain/documents/`,
`infrastructure/`, `presentation/` and its own `composition.py`. Relative imports
stay within the owning version; do not import v1 code from v2 or vice versa.

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

## Current runtime

```text
Version-specific CLI controller
└─ ExtractPdfTextInputBoundary → ExtractPdfTextInteractor → DocumentExtraction
   ├─ PypdfTextExtractor → original PDF bytes
   ├─ UnavailableFallbackExtractor → fallback_unavailable
   ├─ LocalJsonExtractionStore → exact PDF + terminal pages + optional v2 raw reports
   │                            atomic local publication, schema 1/2
   └─ ExtractPdfTextOutputBoundary → JsonCliPresenter → summary/counts/absolute paths
System failures → safe stderr JSON / exit 1, no automatic retry
```

The domain checks blank pages and U+FFFD ratio strictly greater than the original
unreadable threshold. Threshold zero is not force-fallback. v2 additionally detects
suspicious raw text using local Latin/Thai-mark/unusual-character heuristics when
`suspicious_threshold_percent` is configured. It flags strictly above that separate
threshold without changing text/status or requesting fallback; raw reports survive
existing fallback transitions. Missing/null config means not assessed. Rendering,
OCR/vision, font inspection and force-fallback remain deferred. v2 text-only repair
is a separate opt-in command, never an automatic extraction transition.

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
or overwritten. Vision/OCR remain offline; explicit text-only repair has real
client wiring, with integration tests using only a controlled loopback provider.
