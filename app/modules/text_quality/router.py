from fastapi import APIRouter

from app.modules.text_quality.get_thresholds import router as get_thresholds
from app.modules.text_quality.update_thresholds import router as update_thresholds

router = APIRouter(tags=["text_quality"])
router.include_router(get_thresholds)
router.include_router(update_thresholds)
