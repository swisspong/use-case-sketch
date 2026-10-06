# Local PDF text extraction CLI

Uses pypdf and the existing `ExtractPdfTextInteractor`/`DocumentExtraction`.
No API server, IAM integration, rendering, OCR or remote vision calls are included.

## Versions

Source and owning tests are isolated by version:

```text
src/contexts/document_processing/
  v1/  # Preserved baseline
  v2/  # Report-only text detector integrated with CLI/config/storage

tests/unit/contexts/document_processing/{v1,v2}/
tests/integration/contexts/document_processing/{v1,v2}/
```

- `extract-pdf-text` and `extract-pdf-text-v1` run **v1**.
- `extract-pdf-text-v2` runs **v2**.
- v2 adds an opt-in report-only detector for suspicious raw text. Its source uses
  version-local relative imports; it does not depend on or change v1 code.
- Develop improvements only in v2 and its tests; preserve v1 as the comparison
  baseline. Future ideas/undecided behavior are recorded in [NOTES.md](NOTES.md).
- v1 and unassessed v2 runs retain JSON schema 1 and the original summary format.
  Assessed v2 runs use `schema_version: 2` and add summary counts. Schema version
  is not application version. Existing documents are not migrated or overwritten.
- Python imports/module entry points now include `.v1` or `.v2`; the old unversioned
  Python module path is no longer supported. The existing console command remains
  compatible and pinned to v1.

## Install and run

From the repository root (Python 3.10+ and [uv](https://docs.astral.sh/uv/)):

```sh
uv venv backend/.venv
uv pip install --python backend/.venv/bin/python -e backend pytest
backend/.venv/bin/extract-pdf-text /absolute/path/to/input.pdf \
  --config backend/examples/extract_pdf_text_config.json \
  --preset local-offline \
  --data-dir backend/local-documents
```

The equivalent module entry point is:

```sh
backend/.venv/bin/python -m contexts.document_processing.v1.presentation.extract_pdf_text_cli \
  /absolute/path/to/input.pdf \
  --config backend/examples/extract_pdf_text_config.json \
  --preset local-offline --data-dir backend/local-documents
```

To run the independent v2 copy, use the same arguments with
`backend/.venv/bin/extract-pdf-text-v2`, or the module
`contexts.document_processing.v2.presentation.extract_pdf_text_cli`.

Reinstall the editable package after changing console entry points:
`uv pip install --python backend/.venv/bin/python -e backend`.
Both versions can read the current example config; only v2 consumes its
`suspicious_threshold_percent` field (currently `0`). Choose separate `--data-dir`
paths if you want to keep experiments apart. The selected directory's parent must
exist, and sensitive output must stay gitignored. The example config is shared;
use separate config files if the versions need different settings.

All three options are required. Preset lookup is exact; there is no default preset.
The JSON config is a **trusted administrator file**, not upload-supplied configuration.
The example endpoint/model are explicit placeholders for offline operation. Changing
these values does not enable vision: `UnavailableFallbackExtractor` never invokes a
provider. Pages needing fallback are saved with `text: null`, `status: "failed"`,
`method: "vision"`, `failure_code: "fallback_unavailable"` and the selected config's
preset/model metadata. These values do not prove a remote model was invoked.

The configured quality threshold defaults to 60 percent if omitted. Quality rules
remain in the domain: blank pages or a U+FFFD/non-whitespace code-point ratio strictly
above the threshold require fallback. pypdf cannot extract text from scanned images;
this CLI does not OCR them. Fonts/layout, especially Thai font encodings, can affect
extraction correctness. The parser uses strict PDF validation rather than silently
repairing malformed documents.

## v2 detector configuration

Set `"suspicious_threshold_percent": 0` alongside the existing `presets` and
`unreadable_threshold_percent` in the trusted JSON passed through `--config`.
The existing CLI arguments are unchanged; use `extract-pdf-text-v2` or its v2
module entry point. No reinstall is needed for these source changes in an editable install.

- A finite numeric value in `[0, 100]` enables assessment; strings, booleans and
  nonfinite/out-of-range values are configuration failures. Omission or `null`
  disables assessment, preserving schema 1 and the original summary.
- Flags require a suspicious percentage **strictly greater** than the threshold.
  Zero flags any nonzero suspect ratio; equality does not flag. The ratio counts
  the union of suspect non-whitespace code-point positions divided by all
  non-whitespace code points. Blank raw text has a ratio of zero, but still uses
  the original blank-page fallback rule.
- Local rules cover isolated Latin letters adjacent to Thai, orphan/repeated Thai
  marks or multiple tone marks on one base, and U+FFFD/unexpected controls/private
  use. This is a heuristic, not a complete Thai spelling validator or confidence
  score. Legitimate text such as `วิตามินC` may be reported as suspicious.
- Only parser raw text is assessed. Flags do not rewrite text, alter extraction
  status, or trigger extra fallback. OCR/vision and LLM repair remain unavailable.
- Schema 2 adds ordered `raw_text_quality` reports containing `number`, `raw_text`,
  `spans`, counts, `suspicious_percent`, `threshold_percent` and `flagged`. Span
  offsets are zero-based Unicode code points with an exclusive end, referenced
  to the exact stored raw string, not terminal/fallback text or UTF-16 indices.
  Raw text/reports are intentionally retained even if terminal page text becomes
  `null` after fallback failure; treat them as sensitive untrusted data.
- Every run creates a new document identity. Earlier saved results are not
  backfilled; consumers of new assessed runs must support schema 2.

## Output and exit codes

- `0`: one summary JSON on stdout with the document ID, page counts and absolute
  paths to the saved PDF/JSON. Extracted text and per-page details are **not printed**.
  This means the results were saved, **not that all pages extracted successfully**.
- `2`: JSON `{"outcome": "rejected", "code": "invalid_pdf" | "encrypted_pdf" | "invalid_preset"}`
  on stdout, with no saved document. Argument syntax errors also exit 2 via argparse.
- `1`: safe JSON `{"outcome": "error", "code": "system_error"}` on stderr, no success outcome.
  Error responses do not include paths, configuration secrets or raw exceptions.

Example success output (formatted here for readability; the CLI emits one line):

```json
{
  "outcome": "saved",
  "document_id": "<id>",
  "summary": {"total_pages": 3, "extracted_pages": 2, "failed_pages": 1},
  "files": {
    "original_pdf": "/absolute/data-dir/<id>/original.pdf",
    "extraction_json": "/absolute/data-dir/<id>/extraction.json"
  }
}
```

Full extracted text and per-page status/provenance remain in `extraction.json`.
When v2 assessment is enabled, `summary` also contains `assessed_pages` and
`suspicious_pages` (for example, `3` and `1`). No raw text or per-page report is
printed. An absent count means not assessed, not a clean assessment. Consumers
read the file named by `files.extraction_json` and inspect `schema_version`.
CLI flags and exit codes are unchanged; `saved` does not certify text correctness.

JSON strings on stdout escape terminal control characters and non-ASCII characters;
JSON consumers recover the original Unicode paths. Paths/identities may still be
sensitive. Stored extracted text is untrusted and sensitive: do not log it or render
it as trusted HTML.

## Storage and operational limits

```text
<data-dir>/<new-document-id>/
  original.pdf        # Exact original bytes
  extraction.json    # Schema 1, or schema 2 with additional raw text quality reports
```

Supported target: **local Linux/POSIX filesystem with directory fsync, flock and
atomic same-filesystem rename**. Do not use network mounts, Windows or a filesystem
without these semantics and assume the same guarantees.

The data directory's parent must already exist and be a trusted location. New data
and document directories are owner-only (`0700`); new files are owner-only (`0600`).
An existing data directory must belong to the current OS user and must not grant
group/other permissions. A symlink data directory is rejected. Run as a dedicated
non-root user. Access control is OS-user/file-permission based, not multi-user IAM;
the same OS user and privileged users can access the documents. Storage is not
encrypted at rest. Protect the config and source PDFs separately.

Both files are written and fsynced in a private `.staging-*` directory; the staging
directory is fsynced before publication. Cooperating writers lock the data directory,
check identity collisions and atomically rename the complete directory. The data
directory is fsynced before acknowledging success. Normal pre-publication failures
clean up staging; errors after publication do **not** delete the potentially committed
document. There is no automatic retry. If exit 1 occurs after commit/failed output,
inspect saved documents before re-running: a new run creates a new identity.

Abrupt process/machine death can leave private `.staging-*` directories; they are not
published documents. Automatic recovery/retention is not implemented. Clean them
only after stopping all writers. Cleanup failure can also leave private staging.
Durability assumes the filesystem/storage honors fsync; tests exercise real local
filesystem operations and injected failures, not physical power loss.

`backend/local-documents/` is gitignored. If using another directory, keep sensitive
PDFs/JSON out of version control. Deployment, shared-storage migration and automatic
retention/backup are not performed. Parsing is in-process and is not sandboxed or
bounded by upload/page/time limits; use trusted local inputs for now.

## Tests

Install the editable package first so integration tests exercise the installed
version-specific console entry points, not just a manually wired test Interactor.
Both suites check the legacy console alias (pinned to v1) and installed command
routing. v2 adds detector config/schema/summary coverage through actual console
and module entry points, using synthetic PDF mappings rather than private PDFs.
It also extends permissions, failure and concurrency coverage to schema 2.
pytest uses `--import-mode=importlib` so matching test filenames do not collide.

```sh
cd backend
# Run both versions
.venv/bin/python -m pytest tests/unit/contexts/document_processing \
  tests/integration/contexts/document_processing -q
# Preserve the baseline
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v1 \
  tests/integration/contexts/document_processing/v1 -q
# Work on v2
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v2 \
  tests/integration/contexts/document_processing/v2 -q
# Full backend regression
.venv/bin/python -m pytest -q
```

Tests use disposable temporary directories, real PDF bytes/parser and real local
storage. OS/library fault injection covers failure paths; the concurrency case uses
independent writers with a barrier and real filesystem locking. No real vision
provider compatibility, physical crash/power-loss durability or remote guarantees
are claimed.
