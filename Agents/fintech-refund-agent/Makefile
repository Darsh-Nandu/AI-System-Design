.PHONY: up down install migrate seed api lint test clean

UV := uv

up:
	docker compose up -d
	@echo "Waiting for services..."
	@sleep 8

down:
	docker compose down -v

install:
	$(UV) pip install -e ".[dev]"

migrate:
	$(UV) run python -c "import asyncio; from refund_agent.storage.postgres import create_tables; asyncio.run(create_tables())"

seed:
	$(UV) run python -c "import asyncio; from refund_agent.storage.postgres import seed; asyncio.run(seed())"

api:
	$(UV) run refund-api

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests
	$(UV) run mypy src

format:
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

test:
	$(UV) run pytest tests/unit -v

test-all:
	$(UV) run pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage
