# Run from the repo root. Needs uv (Python 3.12) and Node 22 (see frontend/.nvmrc).

.PHONY: install dev api worker frontend test lint check

install:
	cd backend && uv sync
	cd frontend && npm ci

# One command: API on 8050, one worker process, and the app on 3050. Ctrl+C stops all three.
dev:
	@echo "API on http://localhost:8050 (docs at /docs), app on http://localhost:3050"
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && uv run uvicorn --factory app.main:create_app --port 8050 --reload) & \
	(cd backend && uv run python -m app.worker) & \
	(cd frontend && npm run dev) & \
	wait

api:
	cd backend && uv run uvicorn --factory app.main:create_app --port 8050 --reload

# Start more of these in other terminals to see several workers share the queue.
worker:
	cd backend && uv run python -m app.worker

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run typecheck

check: lint test
	cd frontend && npm run build
