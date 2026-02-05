# Lattices Services - Development Commands

default:
    @just --list

# Auto-format code
fmt:
    ruff check --fix src/ tests/
    ruff format src/ tests/

# Run lint checks (read-only)
lint:
    ruff check src/ tests/
    mypy src/

# Run tests with coverage
test *ARGS:
    pytest {{ARGS}}

# Full pipeline: format check + lint + typecheck + tests
check:
    ruff format --check src/ tests/
    ruff check src/ tests/
    mypy src/
    pytest

# Run dev server
dev:
    uvicorn main:app --reload --port 8000 --app-dir src

# Run pre-commit on all files
pre-commit:
    pre-commit run --all-files
