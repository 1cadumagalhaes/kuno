
.PHONY: format format-check lint lint-check lint-unsafe typecheck test run pre-commit check

ARGS :=

ifdef CTX
ARGS += --context $(CTX)
endif

ifdef NS
ARGS += --namespace $(NS)
endif

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

run:
	uv run python -m kuno $(ARGS)

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
