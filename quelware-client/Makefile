lint:
	uv run ruff check .

fix-lint-errors:
	uv run ruff check --fix

fix-lint-errors-unsafe:
	uv run ruff check --fix --unsafe-fixes

format:
	uv run ruff check --select I --fix
	uv run ruff format

format-check:
	uv run ruff check --select I .
	uv run ruff format --check .

unittest:
	uv run pytest -v

typecheck:
	uv run ty check
