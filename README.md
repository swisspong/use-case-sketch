# DocFlow

Vite + React + TypeScript + shadcn/ui frontend, with a FastAPI + async SQLAlchemy + PostgreSQL backend. Redis and Celery remain available in the stack; Settings requests run synchronously as specified in Penpot.

## Run locally

Use Python 3.12+ and Node.js 22.12+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
docker compose -f compose.dev.yaml up -d
```

Set `DATABASE_URL` and a random, stable `LLM_CONFIG_API_KEY_SECRET` in `.env`. Install frontend dependencies once:

```bash
cd frontend
npm ci
cd ..
```

Start the whole development stack from the repository root:

```bash
make dev
```

This starts Postgres and Redis using `compose.dev.yaml`, waits until healthy, applies migrations, and runs FastAPI with reload alongside Vite. Open `http://127.0.0.1:5173`; API documentation is at `http://127.0.0.1:8000/docs`.

Ctrl+C stops the API and frontend. Database containers remain running; `make dev-db-stop` stops them while preserving their data.

Individual commands: `make dev-db`, `make dev-migrate`, `make dev-backend`, `make dev-frontend`, and `make dev-db-logs`. `dev-backend` only runs the API; use `dev-migrate` first when starting it separately. Override ports with `make dev API_PORT=8001 FRONTEND_PORT=5174`; the Vite API proxy follows `API_PORT` automatically.

This is a fresh Settings backend with a new initial migration. Use an empty database, rather than an old per-user prototype database. The historical `backend/` document-processing experiments are independent of the running `app/` API.

## Documents — round one

Open `/documents`, or choose เอกสาร in the sidebar. `/settings` opens Settings; `/` keeps the existing Settings entry point. Frontend hosting must serve `index.html` for these client paths, including `/documents/:id`.

- Select or drop one PDF (up to 20 MiB), then explicitly press อัปโหลด. The server verifies PDF content, rejects damaged/encrypted/empty PDFs, and counts pages.
- Originals and metadata are stored atomically in PostgreSQL. Lists and metadata queries do not load PDF bytes. Documents remain available after refresh/restart when the database volume is retained.
- The list supports newest-first pagination, loading, empty and retry states. Click the filename or row to open persistent document details, then open the exact original PDF.
- Upload failures clear the selected file and progress; no automatic POST retry. Parsing runs in a subprocess that is killed on timeout or request cancellation. Disconnects before completion roll back storage.
- This round deliberately stops before text extraction, quality assessment and OCR. `quality_status: "not_checked"` and `ocr_suggested_count: null` represent that state; the UI never presents it as passed. The full Penpot upload contract's extraction/quality snapshot and per-page results remain for round two.

API: `GET /documents?page=1&page_size=20`, `POST /documents` (multipart `file`), `GET /documents/{id}`, and `GET /documents/{id}/original`. Vite proxies them under `/api`. See [the scope and design notes](docs/documents-round-one.md).

The additive `20261015_documents` migration preserves existing Settings data. `make dev` applies it automatically; use `make dev-migrate` if starting the API separately. PDF support adds `pypdf` and `python-multipart` to the project dependencies.

## Settings behavior

- Four global quality thresholds: integer percentages 0–100, and a nonnegative character count. Defaults come from server settings. PATCH sends only changed fields.
- Global OpenAI-compatible model presets: add, edit, delete, case-insensitive unique names, and exactly one default while presets exist. Deleting default promotes the newest remaining preset.
- API keys are encrypted before storage and are never returned. Blank API key in the edit dialog preserves the existing key.
- Connection tests use a single minimal chat-completion request with a 10-second total timeout. Testing a saved preset closes the database transaction before contacting the provider. Testing is optional and never saves credentials or overrides.
- No authentication or per-user ownership, matching the Penpot Settings contract.

## Verification

Backend tests use disposable real Postgres via Docker, or `TEST_DATABASE_URL` pointing at a dedicated test database (the test schema is recreated).

```bash
.venv/bin/pytest -q
.venv/bin/lint-imports
cd frontend
npm run build
npm run lint
npm run test:e2e
```

See [frontend/README.md](frontend/README.md) for design references and browser-test details.
