.PHONY: db redis services migrate api api-server dev dev-async mcp frontend worker celery-health docker-build docker-up docker-down docker-logs

db:
	docker compose up -d postgres

redis:
	docker compose up -d redis

services:
	docker compose up -d postgres redis

migrate: services
	uv run alembic upgrade head

api: migrate api-server

api-server:
	uv run uvicorn app.main:app --reload

mcp:
	uv run uvicorn app.mcp_server:app --port 8001 --reload

frontend:
	npm --prefix frontend run dev

dev: migrate
	@echo "Starting ParentEase local dev:"
	@echo "- Backend API: http://127.0.0.1:8000"
	@echo "- MCP Server : http://127.0.0.1:8001"
	@echo "- React UI   : http://localhost:5173"
	@$(MAKE) -j3 api-server mcp frontend

dev-async: migrate
	@echo "Starting ParentEase local dev with Celery worker:"
	@echo "- Backend API   : http://127.0.0.1:8000"
	@echo "- MCP Server    : http://127.0.0.1:8001"
	@echo "- React UI      : http://localhost:5173"
	@echo "- Celery Worker : uploads.process_growth_pdf"
	@$(MAKE) -j4 api-server mcp frontend worker

worker: redis
	uv run celery -A app.core.celery_app.celery_app worker --loglevel=info

celery-health: redis
	uv run celery -A app.core.celery_app.celery_app call health.ping

docker-build:
	docker compose -f docker-compose.prod.yml build

docker-up:
	docker compose -f docker-compose.prod.yml up -d

docker-down:
	docker compose -f docker-compose.prod.yml down

docker-logs:
	docker compose -f docker-compose.prod.yml logs -f
