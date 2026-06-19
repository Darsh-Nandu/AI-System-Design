.PHONY: install lint fmt test-unit test-integration test up down attack-demo

install:
	uv pip install -e ".[dev]"

lint:
	ruff check src/ tests/
	mypy src/

fmt:
	ruff format src/ tests/

test-unit:
	SKIP_INTEGRATION=1 pytest tests/unit -v --tb=short --no-cov

test-integration:
	pytest tests/integration -v --tb=short

test:
	pytest tests/ -v --tb=short

up:
	docker compose up -d

down:
	docker compose down -v

attack-demo:
	python -m example.run_attacks
