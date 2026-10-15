"""FastAPI wiring. Endpoints take small deps, never the whole Resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.ports import PdfInspector
from app.modules.llm_config.ports import ConnectionProbe, PresetUow
from app.modules.llm_config.repository import PresetRepo
from app.shared.config import Settings, get_settings
from app.shared.resources import Resources, build_resources, unit_of_work, uow_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.res = build_resources(get_settings())
    try:
        yield
    finally:
        await app.state.res.aclose()


def get_resources(request: Request) -> Resources:
    return request.app.state.res


ResDep = Annotated[Resources, Depends(get_resources)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_session(res: ResDep) -> AsyncIterator[AsyncSession]:
    async with unit_of_work(res) as session:
        yield session


# Commit/rollback before sending a response so immediate refetches see the mutation.
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_connection_probe(res: ResDep) -> ConnectionProbe:
    return res.connection_probe


ConnectionProbeDep = Annotated[ConnectionProbe, Depends(get_connection_probe)]


def get_preset_uow(res: ResDep) -> PresetUow:
    return uow_factory(res, PresetRepo)


PresetUowDep = Annotated[PresetUow, Depends(get_preset_uow)]


def get_pdf_inspector(res: ResDep) -> PdfInspector:
    return res.pdf_inspector


PdfInspectorDep = Annotated[PdfInspector, Depends(get_pdf_inspector)]

# Adapter deps, one per external client, e.g.:
# def get_ocr(res: ResDep) -> TextExtractor: return res.ocr
# OcrDep = Annotated[TextExtractor, Depends(get_ocr)]


async def get_document_thresholds(
    session: SessionDep, settings: SettingsDep
) -> dict[str, int]:
    # Wiring between independent modules; the document owns a plain-value snapshot.
    from dataclasses import asdict

    from app.modules.text_quality.models import Thresholds
    from app.modules.text_quality.repository import ThresholdsRepo

    return asdict(await ThresholdsRepo(session).get() or Thresholds.defaults(settings))


DocumentThresholdsDep = Annotated[dict[str, int], Depends(get_document_thresholds)]
