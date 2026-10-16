# Settings browser coverage

Documents round-one coverage is in `documents.spec.ts`: real upload, reload persistence, original bytes, detail URLs, input validation, drag/drop, failure clearing, loading/empty/retry, real pagination and mobile navigation. Run `npm run test:e2e -- documents.spec.ts` for that slice. See [scope and design notes](../../docs/documents-round-one.md).

Run from `frontend/`: `npm run test:e2e`. Docker is the only external service prerequisite. Playwright starts migrated disposable Postgres, the API on 8011 and Vite on 5174. Do not run multiple copies of this command concurrently because they share these ports and the report directory.

## Public boundaries

Tests use browser-visible controls, HTTP request/response contracts, and a simulated external provider boundary. CRUD and persistence use real FastAPI, encryption, SQLAlchemy and Postgres. Connection tests use the real adapter with `httpx.MockTransport`, never real provider credentials. Browser routes deliberately inject request failures, pending requests and malformed API responses.

| Previously missing cases | Coverage |
| --- | --- |
| 1–2: four fields, invalid values and boundaries | `thresholds.spec.ts`: four parameterized validation/persistence tests and one combined update |
| 3: keyboard, pointer and drag synchronize slider/input | `thresholds.spec.ts`: percentage sliders |
| 4: defaults from server | `thresholds.spec.ts`: loading/server defaults; test server config uses 43 / 7 / 64 / 81 |
| 5: changed fields only; no-op sends nothing | `thresholds.spec.ts`: per-field PATCH payloads and restoring snapshot |
| 6: TQ_001 field error, retained edits and focus | `thresholds.spec.ts`: server field error |
| 7–9: loading, locked saving, no duplicates, navigation during saving | `thresholds.spec.ts`: loading and saving tests |
| 10: native beforeunload | `thresholds.spec.ts`: dirty reload warning, dismiss and retain draft |
| 11–12: presets loading vs empty/error, add while loading | `presets.spec.ts`: delayed list and retry |
| 13: form validation | `presets.spec.ts`: four field tests with empty/length/URL cases |
| 14: create/edit failures preserve draft, retry, field feedback | `presets.spec.ts`: create/edit failure and server validation |
| 15: rotate key; blank edit reuses saved key | `connections.spec.ts`: write-only replacement and saved credentials |
| 16–17: default menu, failure/retry, badge only after confirmation | `presets.spec.ts`: default menu and pending selection |
| 18: disappeared preset | `presets.spec.ts`: default/edit/delete 404; `connections.spec.ts`: saved test 404 |
| 19: configuration conflict | `presets.spec.ts`: create/default 409 and refetch |
| 20–22: non-default deletion, newest-of-three fallback, cancel | `presets.spec.ts`: deletion rules |
| 23: mutation locks and preventing modal dismissal | `presets.spec.ts`: delayed create/edit/delete |
| 24–27: success/latency, authentication, missing model, endpoint, timeout, quota, 5xx | `connections.spec.ts`: provider scenarios; timeout uses real adapter deadline |
| 28: test saved key from editor/menu, temporary overrides | `connections.spec.ts`: saved credentials and menu test |
| 29–30: stale result, saving while test runs, no persistence | `connections.spec.ts`: delayed connection tests |
| 31: keyboard tabs, focus trap/restore, escape/menu | `accessibility.spec.ts`, plus slider keyboard test |
| 32: mobile create/edit/delete and horizontal layout | `accessibility.spec.ts`: 390 × 844 mobile journey |
| 33: network, invalid JSON, unknown error, malformed success | `resilience.spec.ts`: load/save fallback and retry using the latest draft |

`settings.spec.ts` retains the original five combined journeys, including unsaved tab navigation, cancellation, reload persistence, duplicate names and deletion retry.

A separate deterministic backend regression test, `tests/settings/test_commit_boundary.py`, checks that an immediate GET observes a mutation when its success response starts. This catches commit-after-response races without relying on browser/network timing.

## Limits and artifacts

- The suite runs Chromium. Firefox and WebKit are not configured or claimed as covered.
- Mobile checks use a viewport, not a physical phone or touch/IME emulation.
- Screenshots are inspection artifacts, not pixel comparisons against approved baselines.
- Keyboard checks cover concrete workflows, not a complete automated accessibility audit.
- No real vendor integration is exercised; provider compatibility and credentials are separate manual checks through Settings.
- The HTML report is under `playwright-report/`; failed tests retain traces and screenshots under `test-results/`.


`document-detail.spec.ts` additionally covers real two-page PDF rendering, thumbnail
quality indicators, persisted threshold snapshots, page input/navigation/history,
zoom, clipboard, invalid URLs, independent PDF/result retries, stale response
cancellation, reload and mobile overflow.

`document-ocr.spec.ts` covers the OCR action against the real API, renderer, adapter and
Postgres. Only the provider is simulated: `tests/settings_app.py` chooses its behaviour
from the model id (`e2e-ok`, `e2e-ocr-poor`, `e2e-timeout`, `e2e-unavailable`,
`e2e-malformed`), and the test server sets a 2-second OCR deadline. It covers preparing
and running states, the beforeunload warning, compare/tabs, thumbnail updates without a
refetch, and reruns that keep or replace the previous result. It also covers all three
provider failure reasons, DOC_012 (with a link to `/settings?tab=llm`), a preset deleted
mid-request (DOC_013), preset load failure, 500, lost connection and malformed responses.
Every retry is user-initiated, with no automatic resend. It also checks page changes
during OCR and mobile overflow.

The detail suite also uploads PDFs with Thai Unicode mappings to verify the maximum
Thai rule, v3 Latin-substitution detection, exact boundaries and preserved legacy
minimum-Thai labels. Historical UI isolation uses interception; historical API and
migration persistence are verified separately against real PostgreSQL.
