.PHONY: help install lint fmt test test-unit test-integration up down seed

help:
	@echo "  install          Install dependencies"
	@echo "  lint             Run ruff + mypy"
	@echo "  fmt              Format code"
	@echo "  test             All tests"
	@echo "  test-unit        Unit tests (no infra needed)"
	@echo "  test-integration Integration tests"
	@echo "  up               Start Docker Compose stack"
	@echo "  down             Stop stack"
	@echo "  seed             Seed sample legal documents"

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
	python -m example.seed_documents
