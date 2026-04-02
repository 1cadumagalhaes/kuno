
.PHONY: format format-check lint lint-check lint-unsafe typecheck test pre-commit check

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check --fix .

lint-check:
	uv run ruff check .

lint-unsafe:
	uv run ruff check --fix --unsafe-fixes .

typecheck:
	uv run ty check

test:
	uv run pytest

pre-commit:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check
	uv run pytest

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check
	uv run pytest
