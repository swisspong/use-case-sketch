"""Long-lived objects, built once per process (API: lifespan, worker: process init).

When a module gets an adapter: add a field here, build it in build_resources,
close it in aclose. This is the ONLY shared file allowed to import from modules.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.modules.documents.adapters.openai_ocr import OpenAIOcrReader
from app.modules.documents.adapters.page_renderer import LocalPageRenderer
from app.modules.documents.adapters.pdf_inspector import LocalPdfInspector
from app.modules.llm_config.adapters.openai_http import OpenAIConnectionProbe
from app.shared.config import Settings


@dataclass
class Resources:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    connection_probe: OpenAIConnectionProbe
    pdf_inspector: LocalPdfInspector
    page_renderer: LocalPageRenderer
    ocr_reader: OpenAIOcrReader

    async def aclose(self) -> None:
        await self.ocr_reader.aclose()
        await self.connection_probe.aclose()
        await self.engine.dispose()


def build_resources(settings: Settings) -> Resources:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return Resources(
        settings=settings,
        engine=engine,
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
        connection_probe=OpenAIConnectionProbe(),
        pdf_inspector=LocalPdfInspector(),
        page_renderer=LocalPageRenderer(settings.documents_parse_timeout_seconds),
        ocr_reader=OpenAIOcrReader(timeout=settings.documents_ocr_timeout_seconds),
    )


@asynccontextmanager
async def unit_of_work(res: Resources) -> AsyncIterator[AsyncSession]:
    """1 unit of work = 1 transaction. Commit on success, rollback on error.
    Repositories never commit."""
    async with res.sessionmaker() as session, session.begin():
        yield session


def uow_factory[R](
    res: Resources,
    make_repo: Callable[[AsyncSession], R],
) -> Callable[[], AbstractAsyncContextManager[R]]:
    """For multi-transaction handlers: every `async with uow() as repo:` is one
    transaction with a repo bound to it, e.g. uow_factory(res, DocumentRepo)."""

    @asynccontextmanager
    async def _uow() -> AsyncIterator[R]:
        async with unit_of_work(res) as session:
            yield make_repo(session)

    return _uow
