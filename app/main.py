from fastapi import FastAPI

from app.modules.documents.router import router as documents_router
from app.modules.documents.upload_limit import UploadLimitMiddleware
from app.modules.llm_config.router import router as llm_config_router
from app.modules.text_quality.router import router as text_quality_router
from app.shared.config import get_settings
from app.shared.deps import lifespan
from app.shared.errors import register_error_handlers

# from app.modules.<module>.router import router as <module>_router


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(
        UploadLimitMiddleware, max_bytes=get_settings().documents_max_bytes
    )
    app.include_router(documents_router)
    app.include_router(text_quality_router)
    app.include_router(llm_config_router)
    # app.include_router(<module>_router)
    return app


app = create_app()
