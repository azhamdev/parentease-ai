db:
	docker compose up -d postgres

migrate: db
	uv run alembic upgrade head

dev: migrate
	uv run uvicorn app.main:app --reload
