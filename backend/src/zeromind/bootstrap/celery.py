from celery import Celery
from celery.schedules import crontab

from zeromind.shared.config import get_settings

settings = get_settings()
celery_app = Celery(
    "zeromind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["zeromind.bootstrap.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_routes={
        "zeromind.schedule_due_feeds": {"queue": "scheduler"},
        "zeromind.poll_feed": {"queue": "feeds"},
        "zeromind.dispatch_outbox": {"queue": "events"},
    },
    beat_schedule={
        "schedule-due-feeds-every-30-minutes": {
            "task": "zeromind.schedule_due_feeds",
            "schedule": crontab(minute="*/30"),
        },
        "dispatch-outbox-every-minute": {
            "task": "zeromind.dispatch_outbox",
            "schedule": 60.0,
        },
    },
)

