# Repository Guidelines

## Project Structure & Module Organization
- Runtime code lives in `src/radarr_manager/`; subdivide clients, models, CLI helpers, providers, and shared utilities as outlined in the repo guidelines.
- Tests mirror package paths under `tests/` (e.g., `tests/clients/test_calendar.py`) and use fixtures in `tests/fixtures/` for Radarr payloads.
- Keep integration samples in `samples/` and any scratch experiments inside `sandbox/` to avoid polluting the package.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` — create and activate the virtual environment.
- `pip install -e .[dev]` — install project and dev dependencies in editable mode.
- `ruff check .` and `black src tests` — run linting and formatting; apply both before commits.
- `pytest` or `pytest --cov=src/radarr_manager --cov-report=term-missing` — execute the unit suite with optional coverage reporting.
- `python -m radarr_manager.cli sync --dry-run` — validate Radarr interactions locally without modifying the server.

## Coding Style & Naming Conventions
- Target Python 3.12+, 4-space indentation, and module names in `lower_snake_case`; classes use PascalCase; functions, variables, and files prefer snake_case.
- Model API payloads with dataclasses or Pydantic; avoid inline `noqa` unless justified.
- Enforce style with Black (line length 100), Ruff, and isort; keep related prompts and schemas under `src/radarr_manager/providers/`.

## Testing Guidelines
- Use pytest with parametrized cases to cover HTTP edge paths; mirror source layout in file names.
- Mark network-heavy suites with `@pytest.mark.integration` and skip when `RADARR_API_KEY` is unset.
- Maintain >85% branch coverage; record missing lines via `pytest --cov-report=term-missing` and add fixtures for new Radarr responses.

## Commit & Pull Request Guidelines
- Follow Conventional Commit prefixes (e.g., `feat: add calendar sync job`) and keep messages imperative.
- PRs link related issues, list manual verification steps (CLI dry-run, tests), and document new env vars or config changes.
- Attach relevant logs or screenshots for CLI/UI changes and request review for API contract updates to keep documentation in sync.

## Security & Configuration Tips
- Store secrets (API keys, tokens) in environment variables or your `.env`; never commit them.
- Confirm Radarr endpoints and API keys before running integration tests to avoid unintended server updates.
