"""Celery runtime: one event loop + one Resources per worker process.

Never asyncio.run() per task: asyncpg pool connections are bound to the loop
that created them, so the 2nd task would fail with "attached to a different loop".
Built after fork (worker_process_init) so DB sockets are never shared across processes.
"""

import asyncio
from collections.abc import Awaitable, Callable

from celery.signals import worker_process_init, worker_process_shutdown

from app.shared.config import get_settings
from app.shared.resources import Resources, build_resources

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


def run_async[T](fn: Callable[[Resources], Awaitable[T]]) -> T:
    if _loop is None or _res is None:
        raise RuntimeError("worker runtime not initialised")
    return _loop.run_until_complete(fn(_res))
