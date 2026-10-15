---
name: "fastapi-slice-arch"
description: "Scaffold and grow FastAPI + async SQLAlchemy + Celery projects in pragmatic vertical-slice architecture - init project, add module, build each use case test-first one rule at a time."
---

# Pragmatic slice architecture: FastAPI · async SQLAlchemy · Celery

Talk to the user in their language. Code, comments and test names are in English.

Three commands. The user may name them (`init`, `module knowledge`, `usecase knowledge upload document`) or just describe what they want; map it to one of these.

| Command | Does |
|---|---|
| `init` | Writes the project skeleton (shared wiring, worker runtime, test DB, Alembic, CI rules). |
| `module <name>` | Adds an empty module and registers it everywhere it must be registered. |
| `usecase <module> <name>` | Creates a slice and grows it with TDD, one behaviour per cycle, across as many turns or sessions as needed. |

Before any command, read `AGENTS.md` in the repo if it exists: it is the source of truth and may have been edited by the user. If it conflicts with this skill, follow `AGENTS.md` and mention the conflict once.

## The architecture in one screen

- **Modules** (`app/modules/<module>/`) never import each other. No FK or join across modules' tables. Enforced by `lint-imports`.
- **One use case = one slice file** holding its schemas, handler and router. A `SPEC` docstring at the top lists behaviours.
- **Handlers are plain async functions**: no `Depends`, no `HTTPException`, no Celery, no SQLAlchemy. They receive the repos, ports and limits they need.
- **All DB access lives in `<module>/repository.py`.** Only `repository.py` and `models.py` import SQLAlchemy; a handler never sees a session, a statement or a row. Enforced by `lint-imports`.
- **Other layers are added per module only when needed** (see "Growth triggers"), never pre-emptively.
- **Rule levels decide where code and tests go**:

| Level | The rule needs… | Code goes in | Test |
|---|---|---|---|
| 1 | only one entity's own data | method on the model, `models.py` (never queries) | no DB |
| 2 | several things, all already loaded | pure function, `rules.py` (no I/O) | no DB, `parametrize` |
| 3 | the database | query in a repo method (`repository.py`), the decision in the handler, DB constraint as last line of defence | real Postgres `session` |
| 4 | a value that should be changeable | `Settings` field (ops) or a table (admin); logic receives the value as an argument | value: no DB · loading from a table: DB |

Classify by asking, in order: is a number/list here changeable? (→ also level 4) · does it need the DB? (→ 3) · does it combine several things? (→ 2) · else 1.
In handlers, run cheap checks first: level 2 before repo calls.

## `init`

1. Check the target directory. If `app/` already exists, stop and ask whether to merge or use another directory.
2. Write every file under "Templates → init" exactly, then create empty `__init__.py` in `app/`, `app/shared/`, `app/modules/`, `app/worker/`, `tests/`.
3. Alembic: run `alembic init -t async migrations`, then in `migrations/env.py` replace `target_metadata = None` with:
   ```python
   import app.models  # noqa: F401,E402
   from app.shared.config import get_settings  # noqa: E402
   from app.shared.db import Base  # noqa: E402

   config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
   target_metadata = Base.metadata
   ```
4. Ask nothing else. Verify with `lint-imports` (must pass) and `pytest -q` (exit code 5, "no tests collected", is expected at this point).
5. Report in 3–4 lines: what exists, how to start Postgres/Redis (`docker compose -f compose.dev.yaml up -d`), and that the next step is `module <name>`.

If the user's project already has a CI file (e.g. `.gitea/workflows/`), add `lint-imports` and `pytest -q` steps to it rather than creating a new pipeline. Tests need either `TEST_DATABASE_URL` or Docker for testcontainers; on Gitea act_runner that means mounting the Docker socket or running a Postgres service container and setting `TEST_DATABASE_URL`.

## `module <name>`

`<name>` is snake_case, a business area (`knowledge`, `billing`), not a technical layer.

1. Create `app/modules/<name>/` with `__init__.py`, `errors.py`, `models.py`, `repository.py`, `router.py` (templates below) and `tests/<name>/__init__.py`.
2. Register it in three places:
   - `app/models.py`: `from app.modules.<name> import models as _<name>  # noqa: F401`
   - `app/main.py`: import `router as <name>_router` and `app.include_router(<name>_router)`
   - `pyproject.toml`: append `"app.modules.<name>"` to the `independence` contract's `modules` list
3. Table names are prefixed `<name>_` so ownership is visible in the DB.
4. Run `lint-imports` and `pytest -q`. Report in two lines.

No registration is needed for the SQLAlchemy contract: it matches every module by wildcard.

Do not create `rules.py`, `ports.py`, `adapters/`, `domain/` or `tasks.py` yet.

## `usecase <module> <name>`: test-driven growth

The user describes the use case in plain words, possibly one rule at a time and over several sessions. The slice grows until the SPEC is complete.

### Intake (first time only)
- Restate the use case in one line: actor, input, output, side effects.
- Create `app/modules/<module>/<name>.py` in the shape of the reference slice (SPEC docstring, schemas, handler, router) and `tests/<module>/test_<name>.py`; include the slice router in `<module>/router.py`.
- Write the SPEC with only behaviours the user stated, each tagged with its level. You may propose missing behaviours in chat (e.g. "who may do this?", "what if it already exists?"), clearly as suggestions; add them to the SPEC only when the user agrees.
- If the use case only says what happens, start with the happy path.

### One TDD cycle per behaviour
1. **Pick** the next unchecked SPEC item (or the rule the user just gave) and classify its level.
2. **Red**: write one test (or one `parametrize` table) in the test file section for that level. Run only that test. It must fail for the right reason: an assertion or a missing behaviour. If it fails on an import error, add the minimal stub (function signature, empty error class) and run again. Show the failing line to the user in one line.
3. **Green**: write the least code that passes, in the location the level dictates. A level-3 behaviour usually means one new or extended repo method plus one handler line that calls it and decides.
4. **Refactor**: if the handler now holds a level-1 or level-2 rule inline, move it to `models.py` / `rules.py`; if a repo method makes a business decision, move the decision up into the handler. Keep tests green. Check growth triggers.
5. **Verify**: `pytest -q tests/<module>` and `lint-imports`.
6. **Record**: mark the SPEC item `[x]`. Report in at most 3 lines: behaviour, where the code went, test count. Then ask for the next rule or offer the next unchecked item.

Never write code for a behaviour that has no failing test yet. Never mark `[x]` without a passing test. Never change an existing test to make new code pass unless the user agrees the behaviour changed; then update the SPEC line too.

### Endpoint
After the first core behaviour is green, add the endpoint test (`client` fixture, `bearer()` helper): success status and body, one mapped error with its `code`, and missing token → 401. The endpoint body only calls the handler; no `try/except` there.

### Resuming later
When the user returns to a use case, read its SPEC and test file first, run its tests and `lint-imports`, report what is checked and what is not, then continue the cycle. The SPEC is the memory between sessions.

If `lint-imports` reports a slice importing `sqlalchemy` (code written before this rule, or the contract is missing from `pyproject.toml`), add the contract if needed and move those queries into the module's repository first, as a pure refactor with the existing tests kept green, before starting the next behaviour. Tell the user in one line that you did.

### Done
All SPEC items `[x]`, endpoint tested, `pytest -q` and `lint-imports` green. Say so in one line.

## Growth triggers (only when they actually happen)

| Trigger | Add |
|---|---|
| A level-2 rule appears | `<module>/rules.py` |
| `repository.py` passes ~200 lines, or serves clearly separate aggregates | one repo class per aggregate, in a `<module>/repository/` package |
| A changeable value | field `<module>_<name>` in `Settings`; pass it into the handler from the endpoint via `SettingsDep` |
| An external service | `ports.py` + `adapters/` (recipe below) |
| Background work | `tasks.py` (recipe below) |
| Many level-1/2 rules forming a model of their own | `<module>/domain/` |
| A slice file passes ~200 lines | folder `<module>/<use_case>/` with `handler.py`, `schemas.py`, `router.py`; keep the SPEC in `handler.py` |

## Recipes

### Repository
Every DB read and write goes through a repo. The handler asks questions and stores things through it; it never builds a query.

- **Shape**: a concrete class `<Thing>Repo` (e.g. `CollectionRepo`), built with `AsyncSession`. One class per module until the growth trigger. No generic base class, no `get_by(**filters)`, no `execute(stmt)` and no public `session` attribute for handlers to reach through.
- **Methods**: one per real need, named in the module's vocabulary (`count_for_owner`, `add`, `claim_next_pending`), added only when a failing test needs them.
- **Returns**: models, domain dataclasses or plain values. Never `Row`, `Result`, `Select` or a lazy relationship the caller must await.
- **No business decisions**: the repo answers "how many collections does alice have?"; the handler decides "that is over the quota". If a repo method raises a business error other than a translated constraint violation, the decision belongs in the handler.
- **Transactions**: never `commit()` or `rollback()`; the caller's unit of work does. It may `flush()` and open savepoints.
- **Constraint translation** lives here (recipe below), because only the repo knows which constraint it hit.
- **Wiring**: the endpoint builds `ThingRepo(session)` from `SessionDep` (one line, no dep needed). Multi-transaction flows get `uow_factory(res, ThingRepo)` instead (see "External service").
- **Tests**: handler tests pass `ThingRepo(session)` on real Postgres. No fake or in-memory repos, because they drift from real SQL semantics (constraints, NULLs, ordering, upserts). Add a direct repo test only for SQL whose effect the handler tests cannot observe (locking, ordering, an upsert's no-op branch).
- **ORM pitfall**: an ORM `insert(...).returning(Model)` or an upsert may return the object already in the identity map without refreshing it. Return columns, or add `.execution_options(populate_existing=True)`.

### Translating a DB constraint into a business error
In the repo method, wrap the insert in a savepoint so the outer transaction stays usable:
```python
async def add(self, entity: Thing) -> Thing:
    try:
        async with self.session.begin_nested():
            self.session.add(entity)
    except IntegrityError as e:
        raise NameTaken from e
    return entity
```
Test it through the handler: the duplicate raises, and a further insert in the same session still works.

### Errors
- Module errors subclass `Invalid`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict` or `Unavailable` and set a `code`.
- A repo catches only to translate a constraint violation (as above). A handler catches only to recover or persist a failure state. Never log-and-reraise; never `except Exception: return None`.
- Return a result object instead of raising when the caller must branch on it (e.g. `ProcessResult(retry=True)` for Celery).

### External service
1. `ports.py`: a `Protocol` in the module's own vocabulary, a result dataclass, and an error carrying `retryable: bool`.
2. `adapters/<vendor>_http.py`: `httpx.AsyncClient` with an explicit timeout; retry only transient failures (timeouts, connection errors, 408/429/5xx) with exponential backoff + jitter; 4xx and malformed responses raise non-retryable errors; parse the vendor response into the result dataclass in one `_parse` method. Accept `transport=` and `sleep=` constructor arguments for tests. Provide `aclose()`.
3. Wire: field in `Resources`, built in `build_resources`, closed in `aclose`; a small dep in `shared/deps.py` returning the port type.
4. Never call it while a DB transaction is open. Give the handler a unit-of-work factory `uow: Callable[[], AbstractAsyncContextManager[ThingRepo]]`; each `async with uow() as repo:` is one transaction. Split the work: tx1 claims/locks and changes state → call outside any transaction → tx2 records the outcome. The endpoint or task passes `uow_factory(res, ThingRepo)`. If a worker can die mid-call, add a lease (stale `processing` may be reclaimed after N minutes) on the model.
5. Tests: adapter with `httpx.MockTransport` (parses; retries 503 then succeeds; gives up as retryable; 400 not retried; malformed not retried). Handler with a fake port in `tests/fakes.py` and `uow(ThingRepo)` from the fixture. Ports get fakes; repos never do.

### Background task
`<module>/tasks.py`:
```python
from celery import shared_task
from app.shared.resources import uow_factory
from app.worker.runtime import run_async

@shared_task(bind=True, max_retries=5)
def process_x_task(self, x_id: str):
    result = run_async(lambda res: process_x(UUID(x_id), uow_factory(res, XRepo), res.some_port))
    if result.retry:
        raise self.retry(countdown=60 * 2 ** self.request.retries)
    return result.status
```
Handlers called from tasks must be idempotent (a retried task may run twice). Test the handler directly; the task itself only needs a smoke test.

## Templates → init

`pyproject.toml`
```toml
[project]
name = "app"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg",
  "alembic",
  "pydantic-settings",
  "pyjwt",
  "httpx",
  "celery[redis]",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio>=0.26", "testcontainers[postgres]", "import-linter", "ruff"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
testpaths = ["tests"]

[tool.importlinter]
root_package = "app"
include_external_packages = true  # needed to forbid sqlalchemy below

[[tool.importlinter.contracts]]
name = "Modules are independent"
type = "independence"
modules = []  # one entry per module, e.g. "app.modules.knowledge"

[[tool.importlinter.contracts]]
name = "Shared does not depend on modules (except resources wiring)"
type = "forbidden"
source_modules = ["app.shared.config", "app.shared.db", "app.shared.errors", "app.shared.auth"]
forbidden_modules = ["app.modules"]

[[tool.importlinter.contracts]]
name = "Only repositories and models touch SQLAlchemy"
type = "forbidden"
source_modules = ["app.modules"]
forbidden_modules = ["sqlalchemy"]
allow_indirect_imports = true  # slices may import repository/models/shared.deps, just not sqlalchemy itself
ignore_imports = [
  "app.modules.*.repository -> sqlalchemy",
  "app.modules.*.repository.* -> sqlalchemy",
  "app.modules.*.models -> sqlalchemy",
]
unmatched_ignore_imports_alerting = "none"  # a fresh project or module has nothing to match yet
```

`AGENTS.md`
```markdown
# Architecture rules (for humans and AI agents)

Pragmatic vertical slices. Layers are added per module only when complexity demands it.

## Boundaries (enforced by `lint-imports` in CI)
- `app/modules/<a>` never imports `app/modules/<b>`. Cross-module needs go through `app/shared/` or an explicit public function.
- No foreign keys or joins across modules' tables. Store the other module's id as a plain column.
- `app/shared/` holds no business logic. Only `resources.py` / `deps.py` may import module adapters (wiring).

## Slices
- One use case = one file `app/modules/<module>/<use_case>.py`: schemas, handler, router.
- The SPEC docstring at the top lists behaviours; `[x]` only when a test proves it.
- Handlers are plain async functions: no `Depends`, no `HTTPException`, no Celery, no SQLAlchemy. They take the repos/ports/limits they need.
- Endpoints only translate HTTP <-> handler (and build `ThingRepo(session)`). Errors are mapped once by `register_error_handlers`.

## Database (enforced by `lint-imports`)
- All DB access lives in `<module>/repository.py`. Only `repository.py` and `models.py` import SQLAlchemy.
- A repo is a concrete `<Thing>Repo(session)` with one method per real need, named in the module's vocabulary. No generic base, no `execute(stmt)` passthrough.
- Repos return models, domain values or plain values, never rows or statements. They make no business decisions and never commit.
- Multi-transaction flows take `uow_factory(res, ThingRepo)`: each `async with uow() as repo:` is one transaction.

## Where rules live (decide by "what data does the rule need?")
1. One entity's own data -> method on the model (`models.py`). Never queries.
2. Several things, all already loaded -> pure function (`rules.py`). No I/O.
3. Needs the DB -> query in a repo method, decision in the handler, plus a DB constraint as the last line of defence.
4. A changeable value -> `Settings` (ops) or a table (admin). Logic receives the value as an argument.

## Errors
- Raise subclasses of `app.shared.errors` (`Invalid`, `Forbidden`, `NotFound`, `Conflict`, `Unavailable`) with a `code`.
- Catch only to translate (the repo: `IntegrityError` -> `NameTaken`), recover, or persist a failure state. Never log-and-reraise.
- Return a result object instead of raising when the caller must branch on it (e.g. retry).

## External services
- Port (`Protocol`) in `<module>/ports.py`, adapter in `<module>/adapters/`. Adapter owns timeout, retry with backoff, vendor error/response translation.
- Never call an external service while holding a DB transaction: claim (tx) -> call -> record result (tx).
- Clients are built once in `Resources`; endpoints get them through small deps in `shared/deps.py`.

## Tests
- Level 1, 2, 4 logic: no DB. Level 3 + handlers + repos: real Postgres (`session` fixture, rolled back per test). No fake repos.
- Adapters: `httpx.MockTransport`. Handlers using ports: fake ports in `tests/fakes.py`.
- Run `pytest -q` and `lint-imports` before finishing any change.
```

`.env.example`
```bash
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=replace-with-a-long-random-secret
# TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test  # else testcontainers
```

`compose.dev.yaml`
```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment: { POSTGRES_USER: app, POSTGRES_PASSWORD: app, POSTGRES_DB: app }
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
```

`app/shared/config.py`
```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-to-a-long-random-secret-at-least-32b"
    # module settings: <module>_<name>


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`app/shared/db.py`
```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# naming convention -> stable constraint names for Alembic
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
```

`app/shared/errors.py`
```python
"""Error hierarchy: handlers raise these, the outer handler maps them to HTTP once.

Module errors subclass one of these and set `code`, e.g.
    class QuotaExceeded(Conflict): code = "quota_exceeded"
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


class AppError(Exception):
    status = 400
    code = "error"

    def __init__(self, message: str = ""):
        super().__init__(message or self.code)


class Invalid(AppError):
    status, code = 422, "invalid"


class Unauthorized(AppError):
    status, code = 401, "unauthorized"


class Forbidden(AppError):
    status, code = 403, "forbidden"


class NotFound(AppError):
    status, code = 404, "not_found"


class Conflict(AppError):
    status, code = 409, "conflict"


class Unavailable(AppError):
    status, code = 503, "unavailable"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def on_app_error(_: Request, e: AppError) -> JSONResponse:
        return JSONResponse({"code": e.code, "message": str(e)}, status_code=e.status)

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse({"code": "internal_error", "message": "internal error"}, status_code=500)
```

`app/shared/resources.py`
```python
"""Long-lived objects, built once per process (API: lifespan, worker: process init).

When a module gets an adapter: add a field here, build it in build_resources,
close it in aclose. This is the ONLY shared file allowed to import from modules.
"""
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.shared.config import Settings


@dataclass
class Resources:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    # <adapter fields go here>, e.g. ocr: HttpOcrClient

    async def aclose(self) -> None:
        # await self.ocr.aclose()
        await self.engine.dispose()


def build_resources(settings: Settings) -> Resources:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return Resources(
        settings=settings,
        engine=engine,
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
    )


@asynccontextmanager
async def unit_of_work(res: Resources) -> AsyncIterator[AsyncSession]:
    """1 unit of work = 1 transaction. Commit on success, rollback on error.
    Repositories never commit."""
    async with res.sessionmaker() as session, session.begin():
        yield session


def uow_factory[R](
    res: Resources, make_repo: Callable[[AsyncSession], R],
) -> Callable[[], AbstractAsyncContextManager[R]]:
    """For multi-transaction handlers: every `async with uow() as repo:` is one
    transaction with a repo bound to it, e.g. uow_factory(res, DocumentRepo)."""
    @asynccontextmanager
    async def _uow() -> AsyncIterator[R]:
        async with unit_of_work(res) as session:
            yield make_repo(session)
    return _uow
```

`app/shared/deps.py`
```python
"""FastAPI wiring. Endpoints take small deps, never the whole Resources."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import Settings, get_settings
from app.shared.resources import Resources, build_resources, unit_of_work


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.res = build_resources(get_settings())
    yield
    await app.state.res.aclose()


def get_resources(request: Request) -> Resources:
    return request.app.state.res


ResDep = Annotated[Resources, Depends(get_resources)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_session(res: ResDep) -> AsyncIterator[AsyncSession]:
    async with unit_of_work(res) as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Adapter deps, one per external client, e.g.:
# def get_ocr(res: ResDep) -> TextExtractor: return res.ocr
# OcrDep = Annotated[TextExtractor, Depends(get_ocr)]
```

`app/shared/auth.py`
```python
"""Public auth contract used by every module. Token issuing lives in modules/auth."""
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.shared.config import Settings, get_settings
from app.shared.errors import Unauthorized

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str


async def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if cred is None:
        raise Unauthorized("missing token")
    try:
        claims = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise Unauthorized("invalid token") from e
    return CurrentUser(id=claims["sub"], role=claims.get("role", "member"))


UserDep = Annotated[CurrentUser, Depends(current_user)]
```

`app/models.py`
```python
"""Imports every module's models so Base.metadata is complete
(used by Alembic env.py and the test schema). Add one line per module."""
from app.shared.db import Base  # noqa: F401

# from app.modules.<module> import models as _<module>  # noqa: F401
```

`app/main.py`
```python
from fastapi import FastAPI

from app.shared.deps import lifespan
from app.shared.errors import register_error_handlers

# from app.modules.<module>.router import router as <module>_router


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    register_error_handlers(app)
    # app.include_router(<module>_router)
    return app


app = create_app()
```

`app/worker/runtime.py`
```python
"""Celery runtime: one event loop + one Resources per worker process.

Never asyncio.run() per task: asyncpg pool connections are bound to the loop
that created them, so the 2nd task would fail with "attached to a different loop".
Built after fork (worker_process_init) so DB sockets are never shared across processes.
"""
import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from celery.signals import worker_process_init, worker_process_shutdown

from app.shared.config import get_settings
from app.shared.resources import Resources, build_resources

T = TypeVar("T")
_loop: asyncio.AbstractEventLoop | None = None
_res: Resources | None = None


@worker_process_init.connect
def _init(**_):
    init_runtime(build_resources(get_settings()))


@worker_process_shutdown.connect
def _shutdown(**_):
    shutdown_runtime()


def init_runtime(res: Resources) -> None:
    global _loop, _res
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _res = res


def shutdown_runtime() -> None:
    global _loop, _res
    if _loop and _res:
        _loop.run_until_complete(_res.aclose())
        _loop.close()
    _loop = _res = None


def run_async(fn: Callable[[Resources], Awaitable[T]]) -> T:
    if _loop is None or _res is None:
        raise RuntimeError("worker runtime not initialised")
    return _loop.run_until_complete(fn(_res))
```

`app/worker/celery_app.py`
```python
from celery import Celery

from app.shared.config import get_settings

import app.worker.runtime  # noqa: F401  (registers worker_process_init/shutdown)

celery = Celery("app", broker=get_settings().redis_url)
celery.conf.update(task_acks_late=True, worker_prefetch_multiplier=1)
celery.autodiscover_tasks(["app.modules"], related_name="tasks", force=True)
# each module with background work has app/modules/<module>/tasks.py
```

`tests/conftest.py`
```python
"""Test DB: real Postgres. TEST_DATABASE_URL if set, otherwise a testcontainer.

- schema created once per test session
- every test runs inside a transaction that is rolled back (fast, isolated)
- handler code that calls session.begin()/commit works via SAVEPOINTs
"""
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # noqa: F401  (registers all tables)
from app.shared.db import Base


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        yield url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def engine(database_url):
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """Level-3 tests: a session whose work is rolled back after the test."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            await s.close()
            await trans.rollback()


@pytest.fixture
def uow(session):
    """For handlers that take a unit-of-work factory (multi-transaction flows).
    `uow(ThingRepo)` mirrors `uow_factory(res, ThingRepo)`; each block is a savepoint."""
    def make(make_repo):
        @asynccontextmanager
        async def _uow():
            async with session.begin_nested():
                yield make_repo(session)
        return _uow
    return make


@pytest_asyncio.fixture
async def client(session) -> AsyncIterator[AsyncClient]:
    """Endpoint tests: real app, test session, override only what you must."""
    from app.main import create_app
    from app.shared.deps import get_session

    app = create_app()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.app = app  # tests can add more dependency_overrides
        yield c
```

`tests/helpers.py`
```python
from datetime import UTC, datetime, timedelta

import jwt

from app.shared.config import get_settings


def bearer(user_id: str = "u1", role: str = "member") -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode({"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(minutes=5)},
                       get_settings().jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
```


## Templates → module

`app/modules/<module>/errors.py`
```python
from app.shared.errors import Conflict, Invalid, NotFound  # noqa: F401  (import what you use)

# class SomethingTaken(Conflict):
#     code = "something_taken"
```

`app/modules/<module>/models.py`
```python
import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base

# class Thing(Base):
#     __tablename__ = "<module>_things"
#     id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
#     owner_id: Mapped[str] = mapped_column(String(36), index=True)  # no FK across modules
```

`app/modules/<module>/repository.py`
```python
"""All DB access for <module>. One method per real need; never commits (the caller's unit of work does)."""
from sqlalchemy.ext.asyncio import AsyncSession

# from app.modules.<module>.models import Thing


# class ThingRepo:
#     def __init__(self, session: AsyncSession):
#         self.session = session
```

`app/modules/<module>/router.py`
```python
from fastapi import APIRouter

router = APIRouter(tags=["<module>"])
# router.include_router(<use_case>.router)   # one line per slice
```

## Reference slice (shape to follow for every use case)

This is a finished example, verified green against Postgres. Match its structure: SPEC docstring, schemas, handler, router; DB access in the repo; tests grouped by level. Note that the slice file imports nothing from SQLAlchemy.

`app/modules/knowledge/errors.py`
```python
from app.shared.errors import Conflict, Invalid


class CollectionNameInvalid(Invalid):
    code = "collection_name_invalid"


class CollectionNameTaken(Conflict):
    code = "collection_name_taken"


class CollectionQuotaExceeded(Conflict):
    code = "collection_quota_exceeded"
```

`app/modules/knowledge/models.py`
```python
import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class Collection(Base):
    __tablename__ = "knowledge_collections"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)  # no FK across modules
    name: Mapped[str] = mapped_column(String(80))
```

`app/modules/knowledge/rules.py`
```python
"""Level 2: pure rules (no I/O)."""
from app.modules.knowledge.errors import CollectionNameInvalid


def normalize_collection_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not 1 <= len(name) <= 80:
        raise CollectionNameInvalid("name must be 1-80 characters")
    return name
```

`app/modules/knowledge/repository.py`
```python
"""All DB access for knowledge. One method per real need; never commits (the caller's unit of work does)."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.errors import CollectionNameTaken
from app.modules.knowledge.models import Collection


class CollectionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_for_owner(self, owner_id: str) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(Collection).where(Collection.owner_id == owner_id)
        )

    async def add(self, collection: Collection) -> Collection:
        try:
            async with self.session.begin_nested():  # savepoint: a duplicate does not poison the outer tx
                self.session.add(collection)
        except IntegrityError as e:
            raise CollectionNameTaken from e
        return collection
```

`app/modules/knowledge/create_collection.py`
```python
"""Use case: create collection

SPEC (grows one behaviour per TDD cycle; [x] = has a passing test)
- [x] member creates a collection and gets it back            (L3)
- [x] name is trimmed; empty or >80 chars is rejected          (L2)
- [x] name is unique per owner, other owners may reuse it      (L3 + DB constraint)
- [x] max collections per user comes from settings             (L4 → L3)
- [x] POST /knowledge/collections returns 201 / mapped errors  (endpoint)
- [ ] viewer role cannot create                                (L2)
"""
from fastapi import APIRouter, status
from pydantic import BaseModel

from app.modules.knowledge import rules
from app.modules.knowledge.errors import CollectionQuotaExceeded
from app.modules.knowledge.models import Collection
from app.modules.knowledge.repository import CollectionRepo
from app.shared.auth import CurrentUser, UserDep
from app.shared.deps import SessionDep, SettingsDep


class CreateCollectionIn(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: str
    name: str


async def create_collection(
    data: CreateCollectionIn, user: CurrentUser, repo: CollectionRepo, max_per_user: int,
) -> Collection:
    name = rules.normalize_collection_name(data.name)
    if await repo.count_for_owner(user.id) >= max_per_user:
        raise CollectionQuotaExceeded(f"limit {max_per_user}")
    return await repo.add(Collection(owner_id=user.id, name=name))


router = APIRouter()


@router.post("/knowledge/collections", status_code=status.HTTP_201_CREATED, response_model=CollectionOut)
async def create_collection_endpoint(
    data: CreateCollectionIn, user: UserDep, session: SessionDep, settings: SettingsDep,
) -> CollectionOut:
    c = await create_collection(data, user, CollectionRepo(session), settings.knowledge_max_collections_per_user)
    return CollectionOut(id=str(c.id), name=c.name)
```

`app/modules/knowledge/router.py`
```python
from fastapi import APIRouter

from app.modules.knowledge.create_collection import router as create_collection

router = APIRouter(tags=["knowledge"])
router.include_router(create_collection)
```

`tests/knowledge/test_create_collection.py`
```python
import pytest

from app.modules.knowledge import rules
from app.modules.knowledge.create_collection import CreateCollectionIn, create_collection
from app.modules.knowledge.errors import (
    CollectionNameInvalid, CollectionNameTaken, CollectionQuotaExceeded,
)
from app.modules.knowledge.repository import CollectionRepo
from app.shared.auth import CurrentUser
from tests.helpers import bearer

ALICE, BOB = CurrentUser("alice", "member"), CurrentUser("bob", "member")


async def create(session, name, user=ALICE, max_per_user=10):
    return await create_collection(CreateCollectionIn(name=name), user, CollectionRepo(session), max_per_user)


# ---- L2: pure rules ----
@pytest.mark.parametrize("raw,expected", [("  Docs  ", "Docs"), ("a   b", "a b")])
def test_name_is_normalised(raw, expected):
    assert rules.normalize_collection_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "x" * 81])
def test_invalid_name_rejected(raw):
    with pytest.raises(CollectionNameInvalid):
        rules.normalize_collection_name(raw)


# ---- L3: handler + real DB ----
async def test_member_creates_collection(session):
    c = await create(session, " Contracts ")
    assert c.id and c.name == "Contracts" and c.owner_id == "alice"


async def test_name_unique_per_owner(session):
    await create(session, "Docs")
    with pytest.raises(CollectionNameTaken):
        await create(session, "Docs")
    assert (await create(session, "Docs", user=BOB)).owner_id == "bob"


async def test_session_still_usable_after_duplicate(session):
    await create(session, "Docs")
    with pytest.raises(CollectionNameTaken):
        await create(session, "Docs")
    assert await create(session, "Other")


# ---- L4 → L3: limit is injected ----
async def test_quota(session):
    await create(session, "a", max_per_user=2)
    await create(session, "b", max_per_user=2)
    with pytest.raises(CollectionQuotaExceeded, match="limit 2"):
        await create(session, "c", max_per_user=2)


# ---- endpoint: wiring + error mapping ----
async def test_endpoint_created_and_conflict(client):
    r = await client.post("/knowledge/collections", json={"name": "Docs"}, headers=bearer("alice"))
    assert r.status_code == 201 and r.json()["name"] == "Docs"
    r = await client.post("/knowledge/collections", json={"name": "Docs"}, headers=bearer("alice"))
    assert r.status_code == 409 and r.json()["code"] == "collection_name_taken"


async def test_endpoint_requires_token(client):
    r = await client.post("/knowledge/collections", json={"name": "Docs"})
    assert r.status_code == 401
```