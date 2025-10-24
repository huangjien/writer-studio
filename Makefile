# Makefile for writer-studio

UV := uv
PY_SRC := src/writer_studio
TESTS := tests
LINT_TESTS := $(wildcard $(TESTS))
LINT_PATHS := $(PY_SRC) $(LINT_TESTS)

# Default installs both autogen and dev tooling
setup:
	$(UV) sync --extra autogen-stable --extra dev

build:
	$(UV) build

# Run unit tests with coverage (console + HTML)
# Override testpaths to avoid errors when tests/ is missing
# HTML report output: reports/htmlcov
 test:
	$(UV) run pytest --override-ini testpaths= --cov=$(PY_SRC) --cov-report=term-missing --cov-report=html:reports/htmlcov --cov-fail-under=95

# Lint: black check, isort check, flake8 (with explicit line length and ignores)
lint:
	$(UV) run black --check --diff $(LINT_PATHS) || true
	$(UV) run isort --check --diff $(LINT_PATHS) || true
	$(UV) run flake8 --max-line-length 140 --extend-ignore E203,W503 $(LINT_PATHS)

# Format: black and isort
format:
	$(UV) run isort $(LINT_PATHS)
	$(UV) run black $(LINT_PATHS)

# Run API locally with reload
serve-api:
	$(UV) run uvicorn writer_studio.api.server:app --host 0.0.0.0 --port 8000 --reload

.PHONY: setup build test lint format serve-api