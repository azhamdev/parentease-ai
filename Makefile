migrate:
	uv run alembic upgrade head

dev: migrate
	uv run uvicorn app.main:app --reload
