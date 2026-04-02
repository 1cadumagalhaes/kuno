
format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run ty check

test:
	uv run pytest

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check
	uv run pytest
