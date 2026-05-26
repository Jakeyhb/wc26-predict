from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

# Broker auto-detection: Redis if available, otherwise SQLAlchemy+SQLite.
# This avoids requiring Redis in WSL while keeping full Celery Beat scheduling.
_broker = settings.redis_url
_backend = settings.redis_url
if 'redis://' in (_broker or ''):
    try:
        import redis as _redis
        _r = _redis.from_url(_broker)
        _r.ping()
        _r.close()
    except Exception:
        _sqla_url = 'sqla+sqlite:///' + str(settings.model_artifact_dir / 'celery_broker.sqlite')
        _broker = _sqla_url
        _backend = 'db+sqlite:///' + str(settings.model_artifact_dir / 'celery_results.sqlite')

celery_app = Celery(
    'worldcup_predictor',
    broker=_broker,
    backend=_backend,
)
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    imports=('app.workers.tasks',),
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        'max_retries': 10,
        'interval_start': 0,
        'interval_step': 0.2,
        'interval_max': 1,
        'timeout': 30,  # SQLite busy timeout — prevents "database is locked" under concurrent writes
    },
    beat_schedule_filename=str(settings.model_artifact_dir / 'celerybeat-schedule'),
)
celery_app.conf.beat_schedule = {
    'sync-matches-daily': {
        'task': 'app.workers.tasks.sync_matches_task',
        'schedule': crontab(minute=0, hour=4),
    },
    'sync-league-upcoming-daily': {
        'task': 'app.workers.tasks.sync_league_upcoming_task',
        'schedule': crontab(minute=30, hour=5),
    },
    'news-ingest-hourly': {
        'task': 'app.workers.tasks.news_ingest_task',
        'schedule': crontab(minute=0),
    },
    'prediction-trigger-every-30-min': {
        'task': 'app.workers.tasks.prediction_trigger_task',
        'schedule': crontab(minute='*/30'),
    },
    'postmatch-eval-daily': {
        'task': 'app.workers.tasks.postmatch_eval_task',
        'schedule': crontab(minute=0, hour=6),
    },
    'retrain-calibrator-daily': {
        'task': 'app.workers.tasks.retrain_calibrator_task',
        'schedule': crontab(minute=0, hour=2),
    },
    'embed-articles-hourly': {
        'task': 'app.workers.tasks.embed_articles_task',
        'schedule': crontab(minute=30),
    },
}
