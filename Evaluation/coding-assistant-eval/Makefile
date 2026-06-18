.PHONY: help install lint fmt test test-unit test-integration up down seed

help:
	@echo "Available commands:"
	@echo "  install          Install dependencies"
	@echo "  lint             Run ruff + mypy"
	@echo "  fmt              Format code"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests (no infra needed)"
	@echo "  test-integration Run integration tests"
	@echo "  up               Start Docker Compose stack"
	@echo "  down             Stop stack"
	@echo "  seed             Seed sample production logs"

install:
	uv pip install -e ".[dev]"

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

seed:
	python -m example.seed_logs
