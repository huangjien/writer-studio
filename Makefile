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
	$(UV) run pytest --override-ini testpaths= \
		--cov=$(PY_SRC) --cov-config=.coveragerc \
		--cov-report=term-missing --cov-report=html:reports/htmlcov --cov-fail-under=60

# Lint: black check, isort check, flake8 (with explicit line length and ignores)
lint:
	$(UV) run black --check --diff $(LINT_PATHS) || true
	$(UV) run isort --check --diff $(LINT_PATHS) || true
	# Enforce Flake8 line-length 88 (also set in pyproject.toml)
	$(UV) run flake8 --max-line-length 88 $(LINT_PATHS)

# Format: isort, black, and trim trailing whitespace
format:
	$(UV) run isort $(LINT_PATHS)
	$(UV) run black $(LINT_PATHS)
	# Strip trailing whitespace to fix flake8 W291
	find $(PY_SRC) $(TESTS) -type f -name "*.py" -exec sed -i '' -E 's/[[:space:]]+$$//' {} +

# Run API locally with reload
serve-api:
	$(UV) run uvicorn writer_studio.api.server:app --host 0.0.0.0 --port 8000 --reload

.PHONY: setup build test lint format serve-api