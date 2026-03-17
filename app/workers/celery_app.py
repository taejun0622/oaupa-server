from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "oaupa",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.token_refresh",
        "app.workers.webhook_dispatch",
        "app.workers.usage_aggregation",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-expiring-tokens": {
            "task": "app.workers.token_refresh.refresh_expiring_tokens",
            "schedule": 60.0,  # Every 60 seconds
        },
        "cleanup-expired-states": {
            "task": "app.workers.token_refresh.cleanup_expired_states",
            "schedule": 300.0,  # Every 5 minutes
        },
        "aggregate-daily-usage": {
            "task": "app.workers.usage_aggregation.aggregate_daily_usage",
            "schedule": crontab(minute=0, hour=0),  # Midnight UTC
        },
    },
)
