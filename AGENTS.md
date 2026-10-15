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
