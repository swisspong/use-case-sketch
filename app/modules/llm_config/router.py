from fastapi import APIRouter

from app.modules.llm_config.create_preset import router as create_preset
from app.modules.llm_config.delete_preset import router as delete_preset
from app.modules.llm_config.list_presets import router as list_presets
from app.modules.llm_config.set_default_preset import router as set_default_preset
from app.modules.llm_config.test_connection import router as test_connection
from app.modules.llm_config.test_preset import router as test_preset
from app.modules.llm_config.update_preset import router as update_preset

router = APIRouter(tags=["llm_config"])
router.include_router(test_connection)
router.include_router(test_preset)
router.include_router(create_preset)
router.include_router(list_presets)
router.include_router(set_default_preset)
router.include_router(delete_preset)
router.include_router(update_preset)
