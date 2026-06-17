.PHONY: help install lint fmt test test-unit test-integration up down

help:
	@echo "Available commands:"
	@echo "  install          Install dependencies with uv"
	@echo "  lint             Run ruff + mypy"
	@echo "  fmt              Format code with ruff"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests (requires Docker infra)"
	@echo "  up               Start Docker Compose stack"
	@echo "  down             Stop Docker Compose stack"

install:
	uv pip install -e ".[dev,api]"

lint:
	ruff check src/ tests/
	mypy src/

fmt:
	ruff format src/ tests/
	ruff check --fix src/ tests/

test-unit:
	SKIP_INTEGRATION=1 pytest tests/unit -v

test-integration:
	pytest tests/integration -v

test:
	pytest tests/ -v

up:
	docker compose up -d

down:
	docker compose down -v
