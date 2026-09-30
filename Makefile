.PHONY: help setup dev migrate seed ingest-sample test eval lint fmt audit-verify

help:
	@echo "ProtoCite Development Makefile"
	@echo "--------------------------------"
	@echo "  setup         - Install backend and frontend dependencies"
	@echo "  dev           - Run local development services"
	@echo "  migrate       - Run Alembic database migrations"
	@echo "  seed          - Seed initial demo users, branches, and contacts"
	@echo "  ingest-sample - Ingest synthetic protocol corpus"
	@echo "  test          - Run all backend and frontend unit/integration tests"
	@echo "  eval          - Run safety and retrieval evaluation harness"
	@echo "  lint          - Run Ruff and ESLint"
	@echo "  fmt           - Format code with Ruff and Prettier"
	@echo "  audit-verify  - Verify immutable cryptographic audit log chain"

setup:
	cd backend && uv sync
	cd frontend && pnpm install || npm install

dev:
	docker compose up --build

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m scripts.seed

ingest-sample:
	cd backend && uv run python -m scripts.ingest_sample

test:
	cd backend && uv run pytest
	cd frontend && npm test

eval:
	cd backend && uv run python -m eval.run_eval

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

fmt:
	cd backend && uv run ruff format .
	cd frontend && npm run format

audit-verify:
	cd backend && uv run python -m scripts.verify_audit
