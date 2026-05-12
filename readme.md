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
```

Install dependencies:

```bash
uv sync
```

Start PostgreSQL and run migration:

```bash
make migrate
```

Ingest PDFs into local ChromaDB for the first time:

```bash
uv run -m scripts.ingest_pdfs
```

Run backend:

```bash
make dev
```

Backend runs at:

```text
http://127.0.0.1:8000
```

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
20260512_0001 (head)
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

## Redis

Redis is not required for the current local MVP flow.

If needed later:

```bash
redis-server --daemonize yes
redis-cli ping
redis-cli shutdown
```
