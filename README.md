# Radarr Manager

CLI toolkit for sourcing blockbuster releases via LLM providers and synchronizing them with a Radarr instance. The tool discovers trending theatrical movies, normalizes metadata, and optionally enqueues them in Radarr with consistent profiles and tags.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
radarr-manager --help
```

Validate the Radarr pipeline safely with:

```bash
python -m radarr_manager.cli sync --dry-run
```

Set required configuration in your environment or a `.env` file before running discovery commands:

```bash
export RADARR_BASE_URL="http://localhost:7878"
export RADARR_API_KEY="<your-api-key>"
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="<openai-key>"
export OPENAI_MODEL="gpt-4o-mini"
```

The OpenAI provider uses the Responses API with web search enabled so it can pull real-time box office headlines. Any Responses-compatible model that supports the `web_search` tool (e.g. `gpt-4o-mini`, `o4-mini`) will work.

Copy `.env.example` to `.env` for a ready-to-edit template that lists every supported environment variable.

## Development Workflow

Run lint and test checks before opening a PR:

```bash
ruff check .
black src tests
pytest
```

## Configuration Tips

Environment variables override values loaded from `~/.config/radarr-manager/config.toml`. Set `RADARR_MANAGER_CONFIG` to point at a different TOML file when you need project-specific defaults. Use a `.env` file during development and keep secrets (API keys, tokens) out of version control.

Refer to `AGENTS.md` for detailed contributor guidelines.
