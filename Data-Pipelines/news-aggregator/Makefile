.PHONY: up down install migrate worker api seed lint test clean

PYTHON := python
UV := uv

up:
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Services up. Run 'make migrate' next."

down:
	docker compose down -v

install:
	$(UV) pip install -e ".[dev]"
	$(PYTHON) -m spacy download en_core_web_sm

migrate:
	$(UV) run alembic upgrade head

worker:
	$(UV) run aggregator-worker

api:
	$(UV) run aggregator-api

seed:
	$(UV) run python -m news_aggregator.ingestion.producer --seed

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests
	$(UV) run mypy src

format:
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

test:
	$(UV) run pytest tests/unit -v

test-integration:
	$(UV) run pytest tests/integration -v

test-all:
	$(UV) run pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
