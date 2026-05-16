# ParentEase AI

## Backend Setup

Prerequisites:

- Docker Desktop running
- Python environment managed by `uv`

Copy environment template:

```bash
cp .env.example .env
```

Fill API keys in `.env`:

```env
OPEN_ROUTER_API_KEY=your_openrouter_api_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/parentease
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
MCP_SERVER_URL=http://localhost:8001
MCP_TIMEOUT_SECONDS=30
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_BASE_URL="https://us.cloud.langfuse.com"
```

Install dependencies:

```bash
uv sync
```

## Full Local Run

After pulling this branch, run:

```bash
uv sync
cp .env.example .env
```

Fill `.env`, then start services and migrate:

```bash
make migrate
```

Ingest PDFs once for local RAG:

```bash
uv run -m scripts.ingest_pdfs
```

Run the full local stack:

```bash
make dev
```

This starts:

```text
Backend API : http://127.0.0.1:8000
MCP Server  : http://127.0.0.1:8001
React UI    : http://localhost:5173
```

Use the React UI at `http://localhost:5173` for the active MVP frontend.

Backend-only mode:

```bash
make api
```

Optional verification:

```bash
docker compose ps postgres redis
uv run alembic current
docker compose exec -T redis redis-cli ping
uv run celery -A app.core.celery_app.celery_app report
curl http://localhost:8001/health
curl -s -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"tools","method":"tools/list"}'
```

Start PostgreSQL + Redis and run migration:

```bash
make migrate
```

Ingest PDFs into local ChromaDB for the first time:

```bash
uv run -m scripts.ingest_pdfs
```

Run the full local stack:

```bash
make dev
```

Backend runs at:

```text
http://127.0.0.1:8000
```

MCP tool server runs at:

```text
http://127.0.0.1:8001
```

React frontend runs at:

```text
http://localhost:5173
```

MCP tools currently exposed:

```text
calculate_vaccine_schedule
detect_red_flags
search_medical_guidelines
verify_url_source
```

`verify_url_source` uses Tavily to extract article content, then checks article
claims against local RAG chunks and returns a verdict, confidence, claim-level
judgments, and sources.

## Database

Local development uses PostgreSQL through Docker Compose.

Useful commands:

```bash
make db
make migrate
uv run alembic current
docker compose ps postgres
```

Expected Alembic version:

```text
20260515_0004 (head)
```

`parentease.db` is an old/local SQLite file and is not used when `DATABASE_URL` points to PostgreSQL.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

```text
http://localhost:5173
```

## Redis + Celery

Redis is available through Docker Compose. Celery is configured as an M3 foundation for future async upload processing and async tool execution.

Start Redis:

```bash
make redis
docker compose ps redis
```

Run a Celery worker:

```bash
make worker
```

Send a health task from another terminal:

```bash
make celery-health
```

Current note: Celery is a skeleton foundation. The active chat/upload MVP flow does not depend on Celery yet.
