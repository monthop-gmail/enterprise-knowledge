.PHONY: help install test test-all lint typecheck up down schema psql benchmark clean

PY ?= python3
COMPOSE ?= docker compose
DB_URL ?= postgresql://ek:ek@localhost:55433/enterprise_knowledge

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:  ## editable install with dev extras
	$(PY) -m pip install -e '.[dev]'

test:  ## unit tests only (no database, no network)
	$(PY) -m pytest -q -m 'not integration and not mcp'

test-all:  ## every suite, including integration + mcp
	$(PY) -m pytest -q

lint:  ## ruff
	$(PY) -m ruff check src tests evaluation

typecheck:  ## mypy --strict over src
	$(PY) -m mypy

up:  ## start postgres + pgvector
	$(COMPOSE) up -d
	$(COMPOSE) exec -T postgres sh -c 'until pg_isready -U ek >/dev/null 2>&1; do sleep 1; done'

down:  ## stop the stack (keeps the volume)
	$(COMPOSE) down

schema:  ## apply schema.sql (idempotent)
	$(COMPOSE) exec -T postgres psql -U ek -d enterprise_knowledge -v ON_ERROR_STOP=1 < schema.sql

psql:  ## interactive shell
	$(COMPOSE) exec postgres psql -U ek -d enterprise_knowledge

benchmark:  ## offline benchmark (no API cost)
	EK_EMBEDDER=deterministic EK_RERANKER=identity $(PY) -m evaluation.benchmark --mode offline

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + ; rm -rf .pytest_cache .ruff_cache
