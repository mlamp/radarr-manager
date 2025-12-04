# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

Install and run the project:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Testing and quality checks (run before commits):
```bash
ruff check .
black src tests
pytest
pytest --cov=src/radarr_manager --cov-report=term-missing  # with coverage
```

Run the CLI tool:
```bash
radarr-manager --help
radarr-manager discover --limit 3
radarr-manager sync --dry-run  # safe validation mode
python -m radarr_manager.cli sync --dry-run  # alternative invocation
```

## Architecture Overview

This is a Python CLI tool that discovers blockbuster movies using LLM providers and synchronizes them with Radarr media servers.

### Core Components

- **CLI Layer** (`src/radarr_manager/cli/`): Typer-based commands for discovery, sync, and config management
- **Provider System** (`src/radarr_manager/providers/`): Pluggable LLM providers (OpenAI, future Gemini/Grok support)
  - Uses factory pattern in `providers/factory.py` to build providers
  - OpenAI provider uses Responses API with web search for real-time box office data
- **Services** (`src/radarr_manager/services/`): Business logic for discovery and synchronization
- **Radarr Client** (`src/radarr_manager/clients/radarr.py`): HTTP client for Radarr API integration
- **Configuration** (`src/radarr_manager/config/`): Settings from env vars, .env files, and TOML config
- **Smart Discovery** (`src/radarr_manager/discovery/smart/`): LLM orchestrator with specialized agents
  - `orchestrator.py`: GPT-4o orchestrator that coordinates agents via tool calls
  - `agents/`: Specialized agents (FetchAgent, SearchAgent, ValidatorAgent, RankerAgent)
  - `protocol.py`: Agent-to-agent communication via structured markdown with embedded JSON
  - `parsers.py`: Content parsers for IMDB, Rotten Tomatoes, etc.

### Configuration System

The app loads configuration in this order (later values override earlier):
1. `~/.config/radarr-manager/config.toml` (TOML format)
2. `.env` file in project root
3. Environment variables

Key environment variables (copy `.env.example` to `.env`):
- `RADARR_BASE_URL`, `RADARR_API_KEY` - Radarr connection
- `LLM_PROVIDER=openai` - Provider selection
- `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o-mini` - OpenAI config
- `RADARR_QUALITY_PROFILE_ID`, `RADARR_ROOT_FOLDER_PATH` - Sync defaults

### Key Workflow

1. **Discovery**: `DiscoveryService` calls configured provider to get movie suggestions
2. **Sync**: `SyncService` takes suggestions and adds them to Radarr (with duplicate detection)
3. **Provider Pattern**: Factory creates provider instances based on config/CLI overrides

### Smart Agentic Discovery (v1.12.0+)

The `smart_agentic` discovery mode uses an LLM orchestrator pattern:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Smart Orchestrator (GPT-4o)                   │
│  1. Parse user prompt → Understand intent                        │
│  2. Plan strategy → Which agents to call?                        │
│  3. Execute agents → Tool calls                                  │
│  4. Interpret results → Read markdown reports                    │
│  5. Adapt strategy → Handle failures, gaps                       │
│  6. Return final results                                         │
└─────────────────────────────────────────────────────────────────┘
                            │
                   Tool Calls (JSON)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  fetch_movies │   │ search_movies │   │ rank_movies   │
│  (FetchAgent) │   │ (SearchAgent) │   │ (RankerAgent) │
└───────────────┘   └───────────────┘   └───────────────┘
```

Key URLs fetched by the orchestrator:
- `https://www.imdb.com/search/title/?title_type=feature&moviemeter=,50` - IMDB top 50 most popular
- Web search for current box office and trending movies

Quality filtering criteria:
- Wide theatrical release (not limited, festival, or streaming-only)
- High IMDB ratings (7.0+ for mainstream appeal)
- Excludes: K-pop concerts, anime compilations, re-releases, documentaries

### Testing Guidelines

- Tests mirror source structure under `tests/`
- Use `@pytest.mark.integration` for tests requiring live services
- Maintain >85% branch coverage
- Integration tests skip when `RADARR_API_KEY` unset

### Code Style

- Python 3.12+, Black formatting (line length 100), Ruff linting
- Snake_case for modules/functions, PascalCase for classes
- Type hints required, Pydantic models for API payloads
- No inline comments unless justified

### Versioning and Releases

**Single source of truth**: `pyproject.toml` contains the version.

**Version alignment**:
- Git tags: `v{VERSION}` (e.g., `v1.12.0`)
- Docker images: `{VERSION}` (e.g., `1.12.0`) + `latest`

**Release workflow** (use Makefile - single command does everything):
```bash
# Check current version
make version

# Release with version bump (choose one) - does bump + commit + tag + build + push
make release-patch    # 1.12.0 -> 1.12.1
make release-minor    # 1.12.0 -> 1.13.0
make release-major    # 1.12.0 -> 2.0.0
```

**Makefile targets**:
- `make version` - Show current version
- `make release-patch` - Full release: bump patch + commit + tag + docker build + push
- `make release-minor` - Full release: bump minor + commit + tag + docker build + push
- `make release-major` - Full release: bump major + commit + tag + docker build + push
- `make release` - Release current version (tag + build + push, no bump)