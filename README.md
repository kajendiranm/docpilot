# DocPilot

Agentic RAG assistant over engineering docs, with a custom MCP server.
Ask questions in plain English; DocPilot answers from internal docs (with citations), runs read-only SQL for live data, and files GitHub issues.

> Work in progress.

## Quick start (so far)

```bash
cp .env.example .env
docker compose up -d                 # Postgres 16 + pgvector on localhost:5433
cd backend && uv sync
uv run python ../data/seed/seed.py   # demo DB: 10 services, 200 incidents, 300 deployments
uv run python -m ingest.run_ingest --path ../data/docs   # needs GEMINI_API_KEY in .env
uv run pytest && uv run ruff check ..
```
