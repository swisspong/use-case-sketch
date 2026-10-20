"""Imports every module's models so Base.metadata is complete
(used by Alembic env.py and the test schema). Add one line per module."""

from app.modules.documents import models as _documents  # noqa: F401
from app.modules.llm_config import models as _llm_config  # noqa: F401
from app.modules.text_quality import models as _text_quality  # noqa: F401
from app.shared.db import Base  # noqa: F401
# from app.modules.<module> import models as _<module>
