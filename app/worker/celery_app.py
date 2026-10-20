from celery import Celery

import app.worker.runtime  # noqa: F401  (registers worker_process_init/shutdown)
from app.shared.config import get_settings

celery = Celery("app", broker=get_settings().redis_url)
celery.conf.update(task_acks_late=True, worker_prefetch_multiplier=1)
celery.autodiscover_tasks(["app.modules"], related_name="tasks", force=True)
# each module with background work has app/modules/<module>/tasks.py
