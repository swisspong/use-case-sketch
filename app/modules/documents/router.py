from fastapi import APIRouter

from app.modules.documents.get_document import router as get_router
from app.modules.documents.get_page import router as page_router
from app.modules.documents.list_documents import router as list_router
from app.modules.documents.ocr_page import router as ocr_router
from app.modules.documents.upload_document import router as upload_router

router = APIRouter(tags=["documents"])
router.include_router(list_router)
router.include_router(upload_router)
router.include_router(get_router)
router.include_router(page_router)
router.include_router(ocr_router)
