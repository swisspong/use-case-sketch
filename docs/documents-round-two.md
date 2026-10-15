# Documents: extraction and per-page quality

New uploads now validate the PDF, extract text and estimate image coverage for every
page in the existing killable subprocess. Quality assessment uses one snapshot of
the global thresholds read when the upload request starts. The original PDF,
metadata, threshold snapshot and all page results commit atomically. A timeout,
cancellation, disconnect before commit, or database failure saves no partial results.
No OCR provider is called in this increment.

## API and storage

- `POST /documents`: same multipart input and UploadResult envelope; new documents
  have `quality_status: "checked"` and an integer `ocr_suggested_count`.
- `GET /documents`: summaries show the actual number of failing parser pages.
- `GET /documents/{id}`: adds ordered `pages` containing `number`,
  `ocr_suggested`, `has_ocr` and `text_passed`.
- `GET /documents/{id}/pages/{n}`: saved `number`, `thresholds`,
  `parser: {text, quality}` and `ocr: null`.
- `GET /documents/{id}/file`: original PDF for PDF.js; `/original` remains available.
- Missing documents use `404 DOC_007`; missing/unassessed pages use `404 DOC_008`.
  Invalid path types use `422 REQ_001`.

Migrations `20261015_document_pages` and `20261015_thai_max` preserve existing data.
Documents from the storage-only increment keep `quality_status: "not_checked"`, a null suggested
count, and an empty page-summary list. Their viewer works; the results panel explains
that a fresh upload is needed to obtain an assessment. There is no silent backfill
using today's thresholds.

`document_pages` belongs to the documents module and references only its own
`documents` table. List and summary reads omit PDF bytes and extracted page text.
The Settings-to-documents dependency is assembled only in `shared/deps.py`, passing
plain threshold values to the document handler. Repositories never commit.

## Metric definitions and limitations

The design specifies four metric names and threshold directions, but does not define
the statistical algorithms. This increment uses deterministic heuristics:

- `text_chars`: Unicode code points excluding whitespace (not grapheme clusters).
- `thai_percent`: characters in U+0E01–U+0E5B divided by non-whitespace characters.
- `garbled_thai_percent`: problem-character percentage from the historical backend
  v3 detector, ported into `app/modules/documents/text_quality.py`. Detects isolated
  Latin next to Thai (including accented Latin), orphan/repeated/conflicting Thai
  marks, spaces splitting an incomplete Thai syllable, U+FFFD, unexpected controls
  and private-use characters. Positions flagged by several signals count once;
  whitespace never contributes to the count. Normal Thai word endings, English
  words and codes such as `COVID-19` and `B12` are excluded by its rules. This is
  extraction-damage detection, not dictionary spelling or semantic validation;
  legitimate mixed text such as `วิตามินC` can still be flagged. No provider runs.
- `image_percent`: union area of image bounding boxes, clipped to the page crop box,
  divided by visible page area. Counts inline images and nested forms; overlapping
  copies count once. Vector artwork is excluded. Rotated images and clipping paths
  can overestimate visible image coverage.

New uploads suggest OCR if **any one** of these holds:

- `thai_percent > max_thai_percent`
- `garbled_thai_percent > max_garbled_thai_percent`
- `image_percent > max_image_percent`
- `text_chars < min_text_chars`

Equality passes. Empty pages have zero text and zero language percentages;
`min_text_chars` alone determines whether they fail under the new rules. Percentages
round to two decimal places before comparison (`<` fails the character minimum,
`>` fails percentage maxima), so the displayed
values agree with the pass/fail result. `failed` follows the four criteria's UI order.
Changing Settings does not recalculate a previously uploaded document. NUL and
unpaired surrogate characters from PDF extraction become U+FFFD before storage,
preserving their positions and counting them as damaged text.

## Detail UI

Based on Penpot `Document detail` / `Document — Detail` and `Document — Detail / Passed`,
plus `API spec / Document detail` in file `22e416ac-11bb-819d-8008-c9acc3a21110`.

PDF.js renders the PDF and lazy thumbnails from one loading task per document.
The worker, CMaps, fonts and WASM files are bundled/served locally. Detail code loads
only on the detail route. Navigation supports thumbnails, previous/next, page input,
`?page=n`, browser history, and zoom. Bad page URLs fall back to page 1.

The results panel shows the upload-time criteria and saved text, pass/fail markers,
OCR suggestions and copy. Page requests are aborted when changing pages; stale
responses cannot overwrite current results. PDF and result failures have independent
retry controls. The layout stacks on narrow screens. OCR actions and comparison
views belong to the next increment and are not enabled here.

## Verification

Backend tests cover real PDF text/Unicode mapping, blank pages, image overlap,
quality boundaries, persisted snapshots after Settings changes, legacy documents,
missing pages, database constraints and atomic rollback. Existing upload tests retain
validation, subprocess timeout and disconnect/cancellation coverage.

Browser tests cover actual PDF rendering, thumbnail status, navigation/history,
zoom/copy, snapshots, refresh persistence, independent retries, stale responses,
invalid page URLs and mobile overflow. Screenshots are inspection artifacts rather
than approved visual baselines. The suite uses migrated disposable Postgres.

## Transition from minimum to maximum Thai percentage

`20261015_thai_max` renames the global Settings column/constraint and preserves the
saved numeric value. Settings requests and responses use `max_thai_percent`; the old
`min_thai_percent` PATCH field is rejected. Ops defaults now use
`TEXT_QUALITY_DEFAULT_MAX_THAI_PERCENT` (replace the old environment variable if set).

Historical document snapshots retain `min_thai_percent` and their original quality
results and counts. GET page accepts both historical and current snapshot shapes;
the UI shows the old `>=` direction with an explicit historical-result note. They
are not silently relabelled or recalculated with new rules or the new detector.
New uploads use `max_thai_percent` and the ported v3 detector. Fresh upload is the
way to assess an old PDF under the current policy.

The detector's source is
`backend/src/contexts/document_processing/v3/domain/documents/text_quality.py`;
its frozen CLI baseline is unchanged, and the app has no runtime import dependency
on the historical `backend/` package. Regression cases cover its six signal groups,
normal Thai/English counterexamples, overlapping positions, and strict boundaries.
Migration tests exercise upgrade/downgrade against real Postgres and verify old
settings, snapshots, page results and original bytes are preserved.
