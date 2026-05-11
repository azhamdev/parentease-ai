### How to run

1. uv run -m scripts.ingest_pdfs -> for the first time
2. make dev

### frontend
1. rm -rf node_modules package-lock.json
2. npm install
3. npm run dev

### redis
1. redis-server --daemonize yes (running redis)
2. redis-cli ping (check redis : PONG)
3. redis-cli shutdown (shutdown redis)