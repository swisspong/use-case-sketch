# Documents: round one (historical)

The following describes the initial increment. See [round two](documents-round-two.md)
for the current extraction, quality and detail workspace behavior.

Scope: upload a real PDF, retain it after refresh, list documents and open basic details by id. Text extraction, per-page quality results, settings snapshots and OCR belong to subsequent rounds.

## Design references

Read through Penpot MCP on 2026-10-15 from file `22e416ac-11bb-819d-8008-c9acc3a21110`:

- Documents page: `22e416ac-11bb-819d-8008-c9889f417b9c`.
- Documents — Default board: `0a2bc956-b034-80bf-8008-c98a5eb61d9f`, 1440 × 1024.
- API spec / Documents page: `48786bf5-0c9d-80e7-8008-cb0cf6cc9820`.
- Upload states and List states on Documents define file selection, explicit submit, progress, error clearing, list retry, empty state and pagination.

The implementation follows the existing Settings font, zinc palette, 248px sidebar and 48px desktop horizontal padding. File sizes use base 1024 and dates use Asia/Bangkok with the Thai Buddhist calendar. Native links support direct URLs and browser navigation; leaving dirty Settings or an active upload invokes the browser's beforeunload warning.

## Deliberate round-one differences from the full design

Penpot's full POST performs extraction and quality assessment synchronously. This increment validates and stores the PDF only. The summary retains the planned metadata fields and adds `quality_status: "not_checked"`; `ocr_suggested_count` is null until a real assessment exists. Upload copy and success messages describe storage, not extraction. No fabricated quality metrics, success badges or processing statuses are stored.

The detail route currently shows saved metadata and a link to the original. The designed per-page detail workspace is deferred. GET detail/original are the minimal read endpoints for this increment.

## Storage and errors

Postgres stores the original as deferred `bytea`, alongside metadata in the same transaction. Metadata/list reads omit that column. This provides atomic persistence and avoids introducing filesystem compensation or an object store in the first increment. Database storage/backups grow with the PDF collection.

Default file limit is 20 MiB. The request-body middleware bounds multipart input to the file limit plus 64 KiB for its envelope, including requests without Content-Length. A subprocess parses the PDF with strict pypdf validation; the default parsing deadline is 30 seconds. Its cancellation cleanup kills and reaps the process. No LLM provider is contacted.

| Condition | HTTP | error_code |
| --- | --- | --- |
| Non-PDF content | 422 | DOC_001 |
| Oversize PDF/request envelope | 422 | DOC_002 |
| Multiple file parts | 422 | DOC_003 |
| Damaged, encrypted or zero-page PDF | 422 | DOC_004 |
| Missing document | 404 | DOC_005 |
| Parsing deadline | 422 | DOC_006 |
| Invalid query/body | 422 | REQ_001 |

Errors keep the existing `{code, error_code, field?}` convention. Upload failures clear the native input and selected File; selecting again clears the error and does not send a request until submit. GET failures allow explicit retry. A lost response after commit may leave a saved document; automatic retry/idempotency/resume is outside the contract.

## Verification

`tests/documents/test_documents.py` exercises the real PostgreSQL repository and public API, original-byte fidelity, pagination, input limits, filename handling, subprocess deadline, cancellation/disconnect and transactional rollback. Parser tests use real generated PDFs; only the waiting/cancellation port is replaced by a fake in `tests/fakes.py`.

`frontend/e2e/documents.spec.ts` exercises the real upload/list/detail/original journey, reload persistence, client validation, server rejection, drag/drop, upload locking, clearing failures, list states, pagination and mobile navigation. Isolated list/loading/error states use browser interception; persistence tests use the real migrated database. Screenshots are inspection artifacts, not approved visual baselines. The full browser suite also exercises the existing Settings workflows.
