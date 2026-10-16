# DocFlow frontend

React + TypeScript + Vite + Tailwind CSS, scaffolded directly with the official shadcn CLI:

```bash
npx --yes shadcn@latest init -t vite --name frontend --base radix --preset nova --no-monorepo --yes
```

## Development

Run these commands inside `frontend/`:

```bash
npm ci
npm run dev
```

```bash
npm run build
npm run lint
```

The Settings page is implemented against the FastAPI API: global text-quality thresholds and LLM presets, including CRUD, default selection and connection testing. Values are loaded from the API, with no demo presets or client-side defaults.

Components are installed through the shadcn CLI. UI source lives in `src/features/settings/`.

Documents lives in `src/features/documents/`: `/documents` lists and uploads PDFs;
`/documents/:id?page=n` renders the saved PDF with thumbnails, navigation, zoom,
extracted text and quality results against upload-time thresholds. New uploads use
maximum Thai/garbled/image percentages and minimum text length; any failed rule
suggests OCR. Historical minimum-Thai snapshots retain their original labels. PDF.js workers,
CMaps, fonts and WASM assets are hosted locally; detail code loads on demand.
Older documents retain a viewer and an explicit unassessed state. OCR execution and
comparison are deferred. See [round-two scope and metrics](../docs/documents-round-two.md).
`/settings` and `/` keep the Settings entry point; both features share the sidebar.

Vite forwards `/api/*` to `http://127.0.0.1:8000`. Set `API_PROXY_TARGET` to change the local backend address. For a production build, configure a reverse proxy for `/api` or set `VITE_API_BASE_URL` at build time (with corresponding backend CORS configuration if hosted on a different origin).

## Browser tests

From `frontend/`, with Docker running:

```bash
npx playwright install chromium
npm run test:e2e
```

Tests start a disposable Postgres, apply Alembic migrations, verify schema consistency, and start FastAPI plus Vite. They never use the development database or call a real LLM provider. Desktop and mobile screenshots are written under `test-results/`.

No API key, model subscription, or running development servers are required. `tests/settings_app.py` connects the real production adapter to an `httpx.MockTransport` provider, which validates model/credentials and supplies deterministic success, authentication, model, quota, malformed-response and timeout scenarios. The timeout scenario exercises the adapter's real 10-second deadline. Production API code never enables this fixture.

The server also supplies nonstandard configured threshold defaults so the tests detect hardcoded defaults in the UI. Each new test resets state through the public API; suites run sequentially against an isolated test database.

Run a subset or inspect the HTML report:

```bash
npm run test:e2e -- thresholds.spec.ts
npm run test:e2e -- connections.spec.ts
npx playwright show-report
```

See [e2e/README.md](e2e/README.md) for the Settings coverage map and remaining browser/visual limits.

## Settings design reference

Read through Penpot MCP from the `document processing` file:

- File ID: `22e416ac-11bb-819d-8008-c9acc3a21110`
- Page: `Settings` (`918d9ba4-c022-80ab-8008-c9ae2ed22b14`)
- Board: `Settings — Default` (`918d9ba4-c022-80ab-8008-c9af276251f4`)
- Desktop: 1440 × 1024; sidebar: 248px; main padding: 48px horizontal, 40px top; threshold card: 800px wide.
- Font: IBM Plex Sans Thai Looped. Neutral zinc palette; background `#FFFFFF`, sidebar `#FAFAFA`, borders `#E4E4E7`.
- Tabs: เกณฑ์คุณภาพข้อความ / LLM Model.

The adjacent `Settings states` and `Settings / LLM presets` boards define loading, dirty, saving, validation, error, success, confirmation and connection-test behavior.

Official setup reference: https://ui.shadcn.com/docs/installation/vite

## Adding components

To add components to your app, run the following command:

```bash
npx shadcn@latest add button
```

This will place the ui components in the `src/components` directory.

## Using components

To use the components in your app, import them as follows:

```tsx
import { Button } from "@/components/ui/button"
```
