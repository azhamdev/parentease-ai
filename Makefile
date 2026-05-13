db:
	docker compose up -d postgres

redis:
	docker compose up -d redis

services:
	docker compose up -d postgres redis

migrate: services
	uv run alembic upgrade head

dev: migrate
	uv run uvicorn app.main:app --reload

worker: redis
	uv run celery -A app.core.celery_app.celery_app worker --loglevel=info

celery-health: redis
	uv run celery -A app.core.celery_app.celery_app call health.ping
