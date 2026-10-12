# Local PDF text extraction CLI

Uses pypdf and the existing `ExtractPdfTextInteractor`/`DocumentExtraction`.
No API server, IAM integration, rendering, OCR or remote vision calls are included.
v2 additionally offers an explicit text-only OpenAI-compatible repair command;
it never runs automatically during extraction.

## Versions

Source and owning tests are isolated by version:

```text
src/contexts/document_processing/
  v1/  # Preserved baseline
  v2/  # Preserved extraction/repair baseline
  v3/  # Extraction + OCR suggestion (no model) + user-triggered OCR command

tests/unit/contexts/document_processing/{v1,v2,v3}/
tests/integration/contexts/document_processing/{v1,v2,v3}/
```

- `extract-pdf-text` and `extract-pdf-text-v1` run **v1**.
- `extract-pdf-text-v2` runs **v2**.
- v2 adds an opt-in report-only detector for suspicious raw text. Its source uses
  version-local relative imports; it does not depend on or change v1 code.
- `extract-pdf-text-v3` runs **v3**. Text repair (use case, domain proposals,
  adapters, Presenter, CLI and owning tests) is removed from v3; there is no
  `repair-extracted-text-v3` command. v2 repair remains available and unchanged.
- Develop new improvements only in v3 and its tests; preserve v1/v2 as comparison
  baselines. v3 extraction never calls a model: it **suggests** pages for the
  separate, user-triggered `ocr-document-pages-v3` command and saves JSON schema 3.
  Imports are version-local.
- v1 and unassessed v2 runs retain JSON schema 1 and the original summary format.
  Assessed v2 runs use `schema_version: 2` and add summary counts. Schema version
  is not application version. Existing documents are not migrated or overwritten.
- Python imports/module entry points include `.v1`, `.v2` or `.v3`; the old unversioned
  Python module path is no longer supported. The existing console command remains
  compatible and pinned to v1.

## Run v3

From the repository root, run the v3 module directly:

```sh
PYTHONPATH=backend/src backend/.venv/bin/python \
  -m contexts.document_processing.v3.presentation.extract_pdf_text_cli \
  /absolute/path/to/input.pdf \
  --config /trusted/path/document_processing_config.local.json \
  --data-dir backend/local-documents/v3
```

The data directory's parent must already exist and be trusted. Use separate data
paths when comparing versions. Config must be owner-only (`chmod 600`) and uses
the same strict private JSON loader as v2. v3 extraction has **no `--preset`** and
reads only `unreadable_threshold_percent` (default 60) and optional
`suspicious_threshold_percent`; a `presets` catalogue in the same file is ignored
by extraction and read only by the OCR command below.

### v3 OCR suggestion

For every page, v3 counts **problem characters**: the union of non-whitespace
positions flagged by local signals, each counted once:

- `replacement_character` (U+FFFD), `unexpected_control`, `private_use_character`
- `latin_adjacent_to_thai` (font substitution such as `ทีC` = ที่, `เชืMอ` = เชื้อ)
- `thai_mark_sequence` (orphan, repeated or conflicting Thai marks)
- `split_thai_syllable` (whitespace inside a syllable that cannot end there:
  consonant + tone mark with no vowel, e.g. `ป่ วย`, or `เ`+consonant+`ิ/ี/ึ/ื`, e.g.
  `เปิ ด`; ordinary word-final marks such as `ได้ `, `แก่ `, `แพทย์ ` are not counted)

A page is `ocr_suggested` when it is blank (`ocr_reason: "blank_page"`) or its
problem percentage is **strictly above** `unreadable_threshold_percent`
(`ocr_reason: "problem_characters"`). Font-substitution errors usually affect only a
few percent of characters, so use a low threshold (e.g. `1`) to catch them. Parser
text is always saved unchanged; no page is OCR'd automatically.

v3 always saves `schema_version: 3`: each page has `number`, `text`,
`ocr_suggested`, `ocr_reason`, `problem_character_count`,
`non_whitespace_character_count` and `problem_percent`. `raw_text_quality` is added
only when `suspicious_threshold_percent` is set (report-only, as in v2). The stdout
summary is `{"total_pages": N, "ocr_suggested_pages": [...]}` plus
`assessed_pages`/`suspicious_pages` when assessed. Rejections are `invalid_pdf` or
`encrypted_pdf` only.

For console commands and integration tests, reinstall after removing the repair
entry point: `uv pip install --python backend/.venv/bin/python -e backend`.
`extract-pdf-text-v3` remains available; the v3 repair command and module are removed.

### v3 OCR of saved pages (user-triggered)

```sh
ocr-document-pages-v3 <document_id> --preset mfec \
  --config /trusted/path/document_processing_config.local.json \
  --data-dir backend/local-documents/v3 [--pages 2,5]
```

Without `--pages`, every `ocr_suggested` page of the saved document is OCR'd;
explicit pages may include unsuggested ones (`was_suggested: false`). Each page is
rendered with pypdfium2 (200 DPI, longest side ≤ 2000 px, PNG) and sent once, in
document order, to `<preset.endpoint>/chat/completions` (OpenAI-compatible, e.g.
the LiteLLM proxy) with the selected preset's `model`/`api_key` only; no retry, no
environment key, HTTPS verified, plain HTTP only to loopback, 120 s socket timeout.
The model must reply JSON `{"outcome":"text","text":...}` or
`{"outcome":"unreadable"}`. Accepted text must pass the document's **saved**
`threshold_percent` (blank or strictly above -> `unreadable`, text discarded).
Provider/render failures and malformed/truncated replies make only that page
`ocr_unavailable`; later pages continue.

When every selected page is terminal, one attempt is appended atomically as
`<data-dir>/<document_id>/ocr/<attempt_id>.json` (owner-only, attempt
`schema_version: 1`: preset name, model, threshold, pages with status/text/counts;
never the API key). `extraction.json`, `original.pdf` and earlier attempts are never
changed. stdout is a summary only (exit 0):
`{"outcome":"saved","document_id","attempt_id","summary":{"pages","extracted","unreadable","ocr_unavailable"},"files":{"ocr_attempt_json"}}`.
Rejections (exit 2, no OCR/storage): `invalid_preset`, `document_not_found`,
`no_pages_selected`, `page_not_found`, `duplicate_page`, `no_suggested_pages`.
System failures (exit 1) print only `{"outcome":"error","code":"system_error"}`;
they may follow paid OCR calls or a committed attempt file, so do not retry blindly.
Each run sends page images of the document to the configured provider.

The v2 storage guarantees and security behavior documented below also apply to v3;
v2 presets, fallback and schema 1/2 descriptions do not. There is no schema
migration or repair in v3. Existing saved data is not deleted or modified.
Existing v1/v2 commands remain unchanged; the repair documentation below applies
to v2 only.

## v2 shared JSON configuration

The v2 example is now `backend/examples/document_processing_config.json`, shared
by `extract_pdf_text` and `repair_extracted_text`. Each trusted `presets` entry
contains `name`, `endpoint`, `model` and a required nonblank string `api_key`:

```json
{
  "presets": [
    {
      "name": "repair-approved",
      "endpoint": "https://api.openai.com/v1",
      "model": "<approved-model>",
      "api_key": "REPLACE_WITH_YOUR_API_KEY"
    }
  ],
  "unreadable_threshold_percent": 0,
  "suspicious_threshold_percent": 0
}
```

Both real v2 Interactors validate **every** preset before dependency I/O, even
for offline extraction. Missing, blank or non-string keys are configuration
exceptions routed to the outer handler, not business rejections/provider outages.
Only the exact selected preset/key goes to the model port; there is no environment
fallback. Keys are excluded from preset/config repr and
from domain state, persisted results and Output Boundary outcomes.

Both v2 CLI commands load the same trusted JSON schema. Repair uses only the
selected preset's exact `api_key` as Bearer Authorization; there is no separate
key argument or environment lookup. `api_key_env` is not a supported config field.
Extraction vision remains offline. Existing key-free v2 config files must add a
key to every preset. No saved-document migration is needed.

Config must be a current-user-owned regular file without group/other permissions
(e.g. `chmod 600`); final file/parent symlinks are rejected. Its parent path must
be administrator-controlled. Parsing rejects duplicate keys, nonfinite numbers
and files above 16 MiB. Unsafe/malformed config yields only safe stderr/exit 1.
The tracked example contains placeholders only. Create a private, gitignored copy:

```sh
cp backend/examples/document_processing_config.json backend/examples/document_processing_config.local.json
chmod 600 backend/examples/document_processing_config.local.json
# Edit the private copy with your approved endpoint/model/api_key; never log it.
```

`backend/examples/*.local.json` is gitignored. Never commit real keys.
Callers supply only a preset name, not a key/endpoint/model. The new example is
v2-only: v1 remains unchanged and needs its original key-free config schema.

## Install and run

From the repository root (Python 3.10+ and [uv](https://docs.astral.sh/uv/)):

```sh
uv venv backend/.venv
uv pip install --python backend/.venv/bin/python -e backend pytest
backend/.venv/bin/extract-pdf-text /absolute/path/to/input.pdf \
  --config /trusted/path/v1-extraction-config.json \
  --preset local-offline \
  --data-dir backend/local-documents
```

The equivalent module entry point is:

```sh
backend/.venv/bin/python -m contexts.document_processing.v1.presentation.extract_pdf_text_cli \
  /absolute/path/to/input.pdf \
  --config /trusted/path/v1-extraction-config.json \
  --preset local-offline --data-dir backend/local-documents
```

To run the independent v2 copy, use `backend/.venv/bin/extract-pdf-text-v2`, or
`contexts.document_processing.v2.presentation.extract_pdf_text_cli`, with
`--config backend/examples/document_processing_config.local.json` (private copy
prepared above). This does not enable remote vision.

Reinstall the editable package after changing console entry points:
`uv pip install --python backend/.venv/bin/python -e backend`.
The new example is shared between the two v2 use cases, not between versions.
v1's original config uses `name`/`endpoint`/`model` entries without `api_key`;
v1 config loading and tests are outside this implementation's verified scope. Choose
separate config files and `--data-dir` paths for version comparisons. The selected
directory's parent must exist, and sensitive output/config must stay gitignored.
v2 consumes `suspicious_threshold_percent` (currently `0` in the example).

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
  status, or trigger extra fallback. OCR/vision remain unavailable; text repair
  requires the separate explicit command below.
- Schema 2 adds ordered `raw_text_quality` reports containing `number`, `raw_text`,
  `spans`, counts, `suspicious_percent`, `threshold_percent` and `flagged`. Span
  offsets are zero-based Unicode code points with an exclusive end, referenced
  to the exact stored raw string, not terminal/fallback text or UTF-16 indices.
  Raw text/reports are intentionally retained even if terminal page text becomes
  `null` after fallback failure; treat them as sensitive untrusted data.
- Every run creates a new document identity. Earlier saved results are not
  backfilled; consumers of new assessed runs must support schema 2.

## v2 text-only repair and JSON repository

The configured CLI uses the real JSON repository and per-preset JSON credentials
through the OpenAI-compatible adapter. Tests use synthetic keys and a controlled
HTTP/HTTPS server, not a live provider.

Reinstall the editable package to enable the new command:

```sh
uv pip install --python backend/.venv/bin/python -e backend
# Prepare a private chmod-600 JSON config with per-preset api_key as above.
backend/.venv/bin/repair-extracted-text-v2 <saved-document-id> \
  --page 3 --config /trusted/path/model-config.json \
  --preset repair-approved --data-dir backend/local-documents
```

The module entry point is
`contexts.document_processing.v2.presentation.repair_extracted_text_cli`.
Use the **same administrator-controlled `presets` catalogue as extraction**.
For example, the catalogue can include
`{"name":"repair-approved","endpoint":"https://api.openai.com/v1","model":"<approved-text-model>","api_key":"REPLACE_WITH_YOUR_API_KEY"}`.
The caller selects a name, never an endpoint/model. The existing `local-offline`
example is a placeholder and is **not** a working repair provider configuration.
No real provider/document calls are made by the tests or package installation.

Only saved, assessed, flagged `pdf_text` pages are eligible. All exact raw page
text and original spans are sent together once to `<endpoint>/chat/completions`.
Treat this as a document upload: approve the provider's privacy, retention,
capability and costs before running it on real documents. The client uses the
selected preset's JSON `api_key` only. Credentials never enter stored outcomes,
request bodies, stdout or diagnostic messages. The client uses
OpenAI v1 JSON mode (`response_format: {"type":"json_object"}`); compatible
providers must support it and the prompt's `outcome`/`edits` response format.
Unsupported APIs/models are errors, not an invitation to substitute another model.
HTTPS uses standard certificate verification. Plain HTTP is allowed only for
loopback local models; redirects are never followed and requests are never retried.
The default socket-operation timeout is 30 seconds (`--timeout-seconds`, >0 and
<=300). This is not a total deadline or DNS-resolution timeout. `--max-tokens`
sets the positive integer Chat Completions completion budget (default **2048**),
including reasoning for providers that account for it. It does not cap input
costs, guarantee a response within the timeout or guarantee enough tokens for a
valid repair. A `finish_reason: "length"` response is a system/contract error,
never recorded as no-change or partial success; there is no automatic retry.
Providers must support `max_tokens`; unsupported parameters are safe system errors,
not silently removed. Request/response bodies are additionally bounded to 2 MiB
each. Set provider-side budgets/quota separately. Real provider interoperability and
semantic repair accuracy remain unverified by the controlled HTTP tests.

```text
<data-dir>/
  <document-id>/original.pdf         # unchanged
  <document-id>/extraction.json      # unchanged, schema 1/2
  repair-runs/
    <repair-id>/record.json          # append-only repair collection, own schema 1
```

Each successful model decision (`suggested`, `no_changes`, `unrepairable`) creates
one fresh record with `schema_version`, `repair_id`, UTC `created_at`, document/page,
trusted preset/model, outcome and code-point edits. Rejections and system failures
are not audit records. Raw page text is not duplicated: offsets reference the
immutable saved extraction. Suggestions are **not** accepted corrections and are
never applied to the PDF, raw reports or extraction. Neither `no_changes` nor
`unrepairable` certifies correctness.

`RepairRunRepository.save/get/list_by_document` is an application-owned port;
`LocalJsonRepairRunRepository` implements it without DB/ORM dependencies inward.
A future DB adapter can replace it in composition. This is not a general database:
there are no update/delete operations, shared index, cross-record transactions or
pagination. Listing scans published records and is not a point-in-time snapshot.

The repository uses the same local Linux/POSIX assumptions as extraction: private
0700 directories/0600 JSON, fsynced staging then locked collision-check and atomic
rename, followed by collection fsync. Reads reject unsafe final symlinks, shared
permissions, corrupt/misbound records and unrecognized schemas. The root's parent
must be trusted. Atomicity/durability do not extend to remote model calls. Abrupt
process death can leave private `.staging-*` entries, which listing ignores; clean
only with writers stopped. A failed acknowledgement/presentation/stdout may leave
a complete record and an already billed remote call. Inspect history before any
manual retry; automatic retry, rollback of remote effects and deduplication are
not provided. Existing documents are not migrated or modified.

Repair exits: **0** for a recorded model outcome, **2** for `invalid_request`,
`invalid_preset`, `page_not_found`, `vision_page`, `not_assessed`, or `page_not_flagged`,
and **1** for safe stderr `{"outcome":"error","code":"system_error"}`. Stdout
contains only outcome/provenance, document/page, `repair_id`, edit count and an
absolute `files.repair_json` path—not source text, replacement strings or provider
messages. JSON strings escape control/non-ASCII characters. Stored proposals are
sensitive untrusted data; escape appropriately when displaying them.
Authorization is still private-file/current-OS-user based, not multi-user IAM.

## Output and exit codes (extraction)

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
All version suites check the legacy console alias (pinned to v1) and installed
command routing. v3 also verifies that only v2 retains its repair command.
v2 adds detector config/schema/summary coverage through actual console
and module entry points, using synthetic PDF mappings rather than private PDFs.
It also extends permissions, failure and concurrency coverage to schema 2.
pytest uses `--import-mode=importlib` so matching test filenames do not collide.

```sh
cd backend
# Run all three versions
.venv/bin/python -m pytest tests/unit/contexts/document_processing \
  tests/integration/contexts/document_processing -q
# Preserve the baseline
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v1 \
  tests/integration/contexts/document_processing/v1 -q
# Preserve the v2 baseline
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v2 \
  tests/integration/contexts/document_processing/v2 -q
# Work on v3
.venv/bin/python -m pytest tests/unit/contexts/document_processing/v3 \
  tests/integration/contexts/document_processing/v3 -q
# Full backend regression
.venv/bin/python -m pytest -q
```

Tests use disposable temporary directories, real PDF bytes/parser and real local
storage. OS/library fault injection covers failure paths; the concurrency case uses
independent writers with a barrier and real filesystem locking. v3 preserves all
extraction test variants from v2, including credentials and private config errors;
its former chained case now checks an unchanged flagged page without repair history.
Text repair tests remain in v2 only and additionally exercise the configured console/module entry points,
real JSON ports, concurrent publication, pre/post-commit failures and an isolated
loopback HTTP provider (request shape, typed outcomes, timeout, payload bounds,
redirect/error handling, exact selected-key Authorization without environment
credentials, safe config failures, private permissions and secret-free outputs).
A chained extraction-to-repair case uses the same private catalogue and preserves
the original saved PDF/JSON. The provider is controlled test infrastructure, not a
real service. No real vision/text-provider compatibility, semantic repair accuracy,
physical crash/power-loss durability or remote guarantees are claimed.
