# Radarr Manager

CLI toolkit for sourcing blockbuster releases via LLM providers and synchronizing them with a Radarr instance. The tool discovers trending theatrical movies, normalizes metadata, and optionally enqueues them in Radarr with consistent profiles and tags.

## Features

- 🎬 **Intelligent Movie Discovery**: Uses LLM providers (OpenAI) with web search for real-time box office trends
- 🕷️ **Hybrid Discovery Mode (v1.11.0+)**: Combines web scraping with LLM for reliable, comprehensive discovery
  - Scrapes Rotten Tomatoes (theaters + streaming) and IMDB moviemeter
  - Supports Crawl4AI (default) or Firecrawl as scraping backends
  - Merges scraped titles with OpenAI suggestions for best coverage
- 🧠 **Smart Agentic Discovery Mode (v1.6.2+)**: LLM orchestrator coordinates specialized agents
  - GPT-4o orchestrator reasons about which agents to call and in what order
  - Fetches from IMDB moviemeter (top 10/50/100 most popular)
  - Web search for current box office and trending movies
  - Intelligent validation and ranking with quality filtering
  - Excludes low-quality content (concerts, anime compilations, re-releases)
- 🚀 **MCP Service Mode (v1.8.0+)**: Run as MCP server for AI agent integration
  - Long-running service with structured tool API
  - HTTP/SSE transport for network accessibility (v1.9.0+)
  - ENV-based configuration (MCP_HOST, MCP_PORT, MCP_TRANSPORT)
  - Native integration for Telegram bots, Discord bots, web apps
  - 5 MCP tools: search_movie, add_movie, analyze_quality, discover_movies, sync_movies
  - Eliminates CLI overhead, maintains connection pooling
  - Perfect for conversational AI applications
- ➕ **Manual Movie Addition with Quality Gate (v1.7.0)**: Add specific movies by title with smart filtering
  - Intelligent quality gating blocks bad movies (configurable threshold)
  - Override support for guilty pleasures (`--force` flag)
  - Multi-source ratings analysis (RT, IMDb, Metacritic)
  - Detailed quality scores, red flags, and recommendations in JSON
- 🔍 **Deep Analysis Mode (v1.6.0)**: Multi-source ratings validation
  - Quality scoring with configurable thresholds (default: 5.0/10)
  - Red flag detection (poor ratings, low votes, score gaps)
  - Automated filtering of low-quality movies
- 🔄 **Safe Sync Operations**: Dry-run mode for validation before making changes
- ⚙️ **Flexible Configuration**: Environment variables, .env files, or TOML configuration
- 🏷️ **Smart Tagging**: Automatic tagging and quality profile assignment
- 🎯 **Oscar Winner Priority**: Prioritizes movies featuring Academy Award winners
- 🔍 **Duplicate Detection**: Prevents adding movies already in your Radarr library
- 🤖 **Bot-Friendly**: JSON output and exit codes for programmatic integration (Starr Butler, etc.)
- 🧪 **Comprehensive Testing**: 119+ test cases with integration test support

## Requirements

- Python 3.12+
- A running Radarr instance
- OpenAI API key (for movie discovery in `openai`, `hybrid`, or `smart_agentic` mode)
- Crawl4AI or Firecrawl service (optional, for `hybrid`, `scraper`, or `smart_agentic` mode)

## Installation

### Option 1: Docker (Recommended)

```bash
# Pull the latest image
docker pull mlamp/radarr-manager:latest

# Run with environment variables
docker run --rm \
  -e RADARR_BASE_URL="http://your-radarr:7878" \
  -e RADARR_API_KEY="your-api-key" \
  -e OPENAI_API_KEY="your-openai-key" \
  mlamp/radarr-manager:latest discover --limit 5

# Or use a .env file
docker run --rm --env-file .env mlamp/radarr-manager:latest sync --dry-run
```

### Option 2: Python Installation

```bash
# Create virtual environment (Python 3.12+ required)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install for development (includes testing tools)
pip install -e .[dev]

# Or install for production use
pip install -e .
```

## Quick Start

1. **Configure your environment** (copy `.env.example` to `.env`):
```bash
cp .env.example .env
# Edit .env with your API keys and Radarr settings
```

2. **Discover trending movies**:
```bash
radarr-manager discover --limit 5
```

3. **Preview what would be added to Radarr** (safe mode):
```bash
radarr-manager sync --dry-run --limit 3
```

4. **Actually add movies to Radarr** (removes --dry-run):
```bash
radarr-manager sync --limit 3
```

## Configuration

### Environment Variables

Required settings for movie discovery and Radarr sync:

```bash
# Radarr connection
export RADARR_BASE_URL="http://localhost:7878"
export RADARR_API_KEY="<your-radarr-api-key>"

# LLM Provider (currently supports 'openai' or 'static')
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="<your-openai-api-key>"
export OPENAI_MODEL="gpt-4o-mini"  # or gpt-4o, o1-mini

# Optional Radarr sync settings
export RADARR_QUALITY_PROFILE_ID=1
export RADARR_ROOT_FOLDER_PATH="/data/movies"
export RADARR_MINIMUM_AVAILABILITY="announced"
export RADARR_MONITOR=true
export RADARR_TAGS="radarr-manager"

# MCP Service Configuration (v1.9.0+)
export MCP_HOST="127.0.0.1"
export MCP_PORT=8091
export MCP_TRANSPORT="stdio"  # or "sse" for HTTP/SSE transport

# Discovery Mode (v1.11.0+)
export DISCOVERY_MODE="openai"  # openai, hybrid, scraper, or smart_agentic

# Scraper Configuration (for hybrid/scraper modes)
export SCRAPER_PROVIDER="crawl4ai"  # crawl4ai or firecrawl
export SCRAPER_API_URL="http://localhost:11235"  # Crawl4AI default
export SCRAPER_API_KEY=""  # Optional API key
```

### Configuration Files

1. **`.env` file** (recommended for development):
```bash
cp .env.example .env
# Edit .env with your settings
```

2. **TOML configuration** (`~/.config/radarr-manager/config.toml`):
```toml
[radarr]
base_url = "http://localhost:7878"
api_key = "your-radarr-api-key"
quality_profile_id = 1
root_folder_path = "/data/movies"

[provider]
name = "openai"
region = "US"
cache_ttl_hours = 6

[providers.openai]
api_key = "your-openai-api-key"
model = "gpt-4o-mini"
```

**Configuration priority** (highest to lowest):
1. Environment variables
2. `.env` file in project root
3. TOML configuration file
4. Default values

### OpenAI Provider Notes

The OpenAI provider uses the Responses API with web search enabled for real-time box office data. Supported models:
- `gpt-4o-mini` (recommended for cost efficiency)
- `gpt-4o` (higher quality, more expensive)
- `o1-mini` (reasoning model)

## CLI Reference

### Commands

#### `discover`
Discover trending movies without modifying Radarr:

```bash
radarr-manager discover [OPTIONS]

Options:
  --limit INTEGER          Maximum number of movies to return (default: 5)
  --provider TEXT          Override provider (openai, static)
  --discovery-mode TEXT    Discovery mode: openai, hybrid, scraper, smart_agentic, or static (v1.11.0+)
  --debug                  Show detailed discovery output
  --help                   Show this message and exit
```

**Discovery Modes (v1.11.0+):**
- `openai` (default): LLM-based discovery with web search
- `hybrid`: Combines web scraping (RT, IMDB) + OpenAI for comprehensive coverage
- `scraper`: Web scraping only (no OpenAI required)
- `smart_agentic`: LLM orchestrator coordinates specialized agents for highest quality results
- `static`: Built-in test list

#### `sync`
Synchronize discovered movies with Radarr:

```bash
radarr-manager sync [OPTIONS]

Options:
  --limit INTEGER              Number of suggestions to evaluate (default: 5)
  --dry-run / --no-dry-run    Preview without changes (default: --dry-run)
  --force / --no-force        Add even if duplicates detected (default: --no-force)
  --deep-analysis             Enable per-movie quality analysis (v1.6.0+)
  --discovery-mode TEXT       Discovery mode: openai, hybrid, scraper, smart_agentic, or static (v1.11.0+)
  --debug                     Show detailed analysis output
  --help                      Show this message and exit
```

**New in v1.6.0: Deep Analysis Mode**

The `--deep-analysis` flag enables comprehensive per-movie evaluation:
- Fetches ratings from Rotten Tomatoes (critics + audience), IMDb, and Metacritic
- Calculates quality scores (0-10) with weighted ratings
- Detects red flags (poor ratings, low vote counts, score gaps)
- Filters out low-quality movies automatically (score < 6.0 or >2 red flags)

```bash
# Enable deep analysis for quality filtering
radarr-manager sync --limit 10 --dry-run --deep-analysis --debug
```

#### `add`
Manually add a specific movie to Radarr with intelligent quality gating:

```bash
radarr-manager add [OPTIONS]

Options:
  --title TEXT                    Movie title to search for
  --year INTEGER                  Release year (for better accuracy)
  --tmdb-id INTEGER              TMDB ID (e.g., 123456)
  --imdb-id TEXT                 IMDB ID (e.g., tt1234567)
  --dry-run / --no-dry-run       Preview without changes (default: --dry-run)
  --force / --no-force           Bypass quality gate and add regardless (default: --no-force)
  --deep-analysis / --no-deep    Enable quality analysis (default: --deep-analysis)
  --quality-threshold FLOAT      Minimum score (0-10) to auto-add (default: 5.0)
  --json / --no-json             Output as JSON (default: --json)
  --debug                        Enable debug logging
  --help                         Show this message and exit
```

**New in v1.7.0: Intelligent Quality Gating**

The `add` command now includes smart quality filtering that protects your library from bad movies while allowing voice override for guilty pleasures:

- **Quality Gate**: Movies below `--quality-threshold` (default 5.0/10) are blocked
- **Multi-Source Ratings**: RT critics/audience, IMDb, Metacritic analysis
- **Override Support**: Use `--force` to bypass quality gate
- **Detailed Feedback**: JSON includes quality scores, red flags, and override instructions

**Usage Examples:**

```bash
# Basic add with quality gate (deep-analysis enabled by default)
radarr-manager add --title "Dune: Part Three" --year 2026 --no-dry-run

# Skip quality checks for fast add
radarr-manager add --title "The Batman Part II" --year 2026 --no-deep-analysis --no-dry-run

# Custom quality threshold (stricter filtering)
radarr-manager add --title "Borderline Movie" --year 2024 --quality-threshold 7.0

# Force add a low-quality movie (override quality gate)
radarr-manager add --title "Movie 43" --year 2013 --force --no-dry-run

# Add by TMDB ID (most accurate, skips quality analysis)
radarr-manager add --tmdb-id 123456 --no-deep-analysis --no-dry-run

# Human-readable output
radarr-manager add --title "Interstellar" --year 2014 --no-json
```

**JSON Output Format:**

Success with quality analysis:
```json
{
  "success": true,
  "message": "Successfully added: Dune: Part Three (2026)",
  "movie": {
    "title": "Dune: Part Three",
    "year": 2026,
    "tmdb_id": 1170608,
    "imdb_id": "tt15239678"
  },
  "quality_analysis": {
    "overall_score": 8.5,
    "threshold": 5.0,
    "passed": true,
    "recommendation": "RECOMMENDED - Strong quality, worth adding",
    "ratings": {
      "rotten_tomatoes": {
        "critics_score": 92,
        "audience_score": 89
      },
      "imdb": {
        "score": 8.7,
        "votes": 125000
      },
      "metacritic": {
        "score": 85
      }
    },
    "red_flags": []
  }
}
```

Quality gate rejection:
```json
{
  "success": false,
  "error": "quality_too_low",
  "message": "Movie has poor ratings (score: 2.5/10, threshold: 5.0)",
  "movie": {
    "title": "Movie 43",
    "year": 2013,
    "tmdb_id": 63535
  },
  "quality_analysis": {
    "overall_score": 2.5,
    "threshold": 5.0,
    "passed": false,
    "recommendation": "NOT RECOMMENDED - Quality concerns, likely skip",
    "ratings": {
      "rotten_tomatoes": {
        "critics_score": 4,
        "audience_score": 18
      },
      "imdb": {
        "score": 4.3,
        "votes": 95420
      },
      "metacritic": {
        "score": 18
      }
    },
    "red_flags": [
      "Extremely low critic consensus (Rotten Tomatoes: 4%)",
      "IMDb rating below 5.0 indicates poor quality",
      "Metacritic in 'overwhelming dislike' range (< 40)"
    ]
  },
  "can_override": true,
  "override_instructions": "To add this movie anyway, use: radarr-manager add --title \"Movie 43\" --year 2013 --force"
}
```

Already exists:
```json
{
  "success": false,
  "error": "already_exists",
  "message": "Movie already in Radarr library: Inception (2010)",
  "movie": {
    "title": "Inception",
    "year": 2010,
    "tmdb_id": 27205
  },
  "override_instructions": "This check cannot be bypassed with --force"
}
```

Force override (with warning):
```json
{
  "success": true,
  "message": "Successfully added: Movie 43 (2013)",
  "warning": "This movie has poor ratings but was added due to --force flag",
  "movie": {
    "title": "Movie 43",
    "year": 2013,
    "tmdb_id": 63535,
    "imdb_id": "tt1667003"
  },
  "quality_analysis": {
    "overall_score": 2.5,
    "threshold": 5.0,
    "passed": false,
    "recommendation": "NOT RECOMMENDED - Quality concerns, likely skip",
    "ratings": {...},
    "red_flags": [...]
  }
}
```

**Exit Codes:**
- `0`: Success
- `1`: Movie not found
- `2`: Already exists (duplicate)
- `3`: Quality too low (with --deep-analysis)
- `4`: Radarr API error
- `5`: Other errors

**Integration with Starr Butler:**

The `add` command is designed for programmatic use by voice bots and automation tools. The JSON output and exit codes make it easy to integrate:

```bash
# Example: Telegram bot calling radarr-manager via Docker
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:latest \
  add --title "Movie Title" --year 2026 --no-dry-run
```

#### `config`
Display current configuration:

```bash
radarr-manager config [OPTIONS]

Options:
  --show-sources     Display configuration sources
  --help            Show this message and exit
```

### Example Workflows

**Safe exploration** (no changes to Radarr):
```bash
radarr-manager discover --limit 10
radarr-manager sync --dry-run --limit 5
```

**Hybrid discovery with web scraping (v1.11.0+)**:
```bash
# Start Crawl4AI container (required for hybrid/scraper modes)
docker compose -f docker-compose.dev.yml up -d

# Discover movies using hybrid mode (scraper + OpenAI)
radarr-manager discover --discovery-mode hybrid --limit 20 --debug

# Sync with hybrid discovery
radarr-manager sync --discovery-mode hybrid --limit 15 --no-dry-run
```

**Smart agentic discovery (v1.6.2+)** - highest quality results:
```bash
# Start Crawl4AI container (required for smart_agentic mode)
docker compose -f docker-compose.dev.yml up -d

# Discover movies using smart agentic mode (LLM orchestrator + agents)
radarr-manager discover --discovery-mode smart_agentic --limit 10 --debug

# Sync with smart agentic discovery
radarr-manager sync --discovery-mode smart_agentic --limit 10 --no-dry-run
```

The smart agentic mode uses a GPT-4o orchestrator that:
1. Fetches from IMDB moviemeter (top popular movies)
2. Searches for current box office and trending movies
3. Validates and filters out low-quality content
4. Ranks by mainstream appeal and quality (IMDB 7+)

**Deep analysis with quality filtering (v1.6.0+)**:
```bash
# Analyze movies with multi-source ratings validation
radarr-manager sync --limit 10 --dry-run --deep-analysis --debug
```

**Production sync** (adds movies to Radarr):
```bash
radarr-manager sync --limit 3
```

**Production sync with deep analysis** (recommended):
```bash
radarr-manager sync --limit 10 --no-dry-run --deep-analysis
```

**Force add duplicates**:
```bash
radarr-manager sync --force --limit 2
```

## MCP Service Mode

Run radarr-manager as a long-running MCP (Model Context Protocol) server for AI agent integration. Perfect for Telegram bots, Discord bots, or any LLM application that needs to interact with Radarr.

For comprehensive MCP documentation including client integration, all tools, and examples, see **[MCP.md](MCP.md)**.

### Why MCP Mode?

**CLI Approach** (subprocess overhead):
```python
# Telegram bot calling CLI
result = subprocess.run(['radarr-manager', 'add', '--title', title])
# New process per request, parse JSON output
```

**MCP Approach** (clean, fast):
```python
# Telegram bot using MCP client
result = await mcp_client.call_tool("add_movie", {"title": title, "year": 2026})
# Structured response, persistent service
```

### Transport Modes (v1.9.0+)

**stdio** (default): Process communication for local clients
```bash
radarr-manager serve  # stdio transport
```

**sse**: HTTP/SSE server for network-accessible service
```bash
radarr-manager serve --transport sse --host 0.0.0.0 --port 8091
```

Endpoints: `/mcp/sse` (SSE stream), `/mcp/messages` (POST)

### Available MCP Tools

| Tool | Description | Use Case |
|------|-------------|----------|
| `search_movie` | Check if movie exists in Radarr | "Do we have this movie?" |
| `add_movie` | Add with quality gating | "Add Dune: Part Three" |
| `analyze_quality` | Get ratings without adding | "Is this movie good?" |
| `discover_movies` | Find blockbuster suggestions | "What's trending?" |
| `sync_movies` | Discover and sync in one call | "Add top 10 movies" |

### Environment Configuration (v1.9.0+)

```bash
# MCP Service Configuration
MCP_HOST=127.0.0.1           # Bind host (default: 127.0.0.1)
MCP_PORT=8091                # Bind port (default: 8091)
MCP_TRANSPORT=sse            # Transport mode: stdio or sse (default: stdio)
```

CLI flags override ENV variables.

### Start MCP Server

```bash
# Start with stdio transport (local clients)
radarr-manager serve

# Start with HTTP/SSE transport (network accessible)
radarr-manager serve --transport sse --host 0.0.0.0 --port 8091

# With debug logging
radarr-manager serve --transport sse --host 0.0.0.0 --debug
```

### Docker MCP Service

```bash
# Run as long-running HTTP/SSE service
docker run -d \
  --name radarr-manager-mcp \
  --env-file .env \
  -p 8091:8091 \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=8091 \
  -e MCP_TRANSPORT=sse \
  mlamp/radarr-manager:latest \
  serve --transport sse --host 0.0.0.0 --debug

# Check logs
docker logs -f radarr-manager-mcp

# Connect to MCP endpoints
# SSE stream: http://localhost:8091/mcp/sse
# POST messages: http://localhost:8091/mcp/messages
```

### Python Client Example

```python
from mcp import Client

# Connect to MCP server
async with Client("stdio://radarr-manager serve") as mcp:
    # Check if movie exists
    result = await mcp.call_tool("search_movie", {
        "title": "Interstellar",
        "year": 2014
    })
    print(result["exists"])  # True/False

    # Add movie with quality gate
    result = await mcp.call_tool("add_movie", {
        "title": "Dune: Part Three",
        "year": 2026,
        "dry_run": False,
        "quality_threshold": 6.0
    })

    if result["error"] == "quality_too_low":
        # Ask user if they want to force add
        print(f"⚠️ Low quality: {result['quality_analysis']['overall_score']}/10")
        print(result["override_instructions"])

        # Force add if user confirms
        result = await mcp.call_tool("add_movie", {
            "title": "Dune: Part Three",
            "year": 2026,
            "force": True
        })
```

### Telegram Bot Integration

```python
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler
from mcp import Client

mcp_client = Client("stdio://radarr-manager serve")

async def handle_voice(update: Update, context):
    # 1. Transcribe voice message
    audio = await update.message.voice.get_file()
    transcript = await openai.audio.transcribe("whisper-1", audio)

    # 2. Parse movie request
    parsed = await parse_movie_request(transcript)

    # 3. Check if exists via MCP
    result = await mcp_client.call_tool("search_movie", {
        "title": parsed["title"],
        "year": parsed["year"]
    })

    if result["exists"]:
        await update.message.reply_text(f"✅ We already have {parsed['title']}!")
        return

    # 4. Add with quality gate
    result = await mcp_client.call_tool("add_movie", parsed)

    if result["success"]:
        await update.message.reply_text(f"✅ Added {parsed['title']}!")
    elif result["error"] == "quality_too_low":
        qa = result["quality_analysis"]
        await update.message.reply_text(
            f"⚠️ {parsed['title']} has poor ratings "
            f"(score: {qa['overall_score']}/10)\n"
            f"Reply 'yes' to add anyway."
        )

# Register handler
app = Application.builder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.run_polling()
```

### MCP Response Examples

**Successful Add:**
```json
{
  "success": true,
  "message": "Added: Dune: Part Three (2026)",
  "movie": {"title": "Dune: Part Three", "year": 2026, "tmdb_id": 12345},
  "quality_analysis": {
    "overall_score": 8.5,
    "threshold": 5.0,
    "passed": true,
    "recommendation": "HIGHLY RECOMMENDED",
    "ratings": {
      "rotten_tomatoes": {"critics_score": 85, "audience_score": 90},
      "imdb": {"score": 8.3, "votes": 250000},
      "metacritic": {"score": 78}
    },
    "red_flags": []
  }
}
```

**Quality Gate Rejection:**
```json
{
  "success": false,
  "error": "quality_too_low",
  "message": "Movie has poor ratings (score: 3.2/10, threshold: 5.0)",
  "quality_analysis": {
    "overall_score": 3.2,
    "threshold": 5.0,
    "passed": false,
    "recommendation": "NOT RECOMMENDED",
    "red_flags": ["RT critics score very poor (15%)", "Large RT score gap (critics: 15% vs audience: 45%)"]
  },
  "can_override": true,
  "override_instructions": "To add anyway, call add_movie again with force=true"
}
```

## Docker Usage

The Docker image is available at `mlamp/radarr-manager` on Docker Hub with multi-architecture support (amd64, arm64).

For comprehensive Docker documentation including advanced usage, networking, and scheduling, see **[DOCKER.md](DOCKER.md)**.

### Quick Start with Docker

**Discover movies:**
```bash
docker run --rm \
  -e RADARR_BASE_URL="http://192.168.1.100:7878" \
  -e RADARR_API_KEY="your-radarr-api-key" \
  -e OPENAI_API_KEY="your-openai-api-key" \
  mlamp/radarr-manager:latest discover --limit 10
```

**Sync with deep analysis (recommended):**
```bash
docker run --rm \
  --env-file /path/to/.env \
  --network host \
  mlamp/radarr-manager:latest \
  sync --limit 10 --no-dry-run --deep-analysis --debug
```

See **[DOCKER.md](DOCKER.md)** for detailed examples, networking options, and docker-compose configurations.

## Development Workflow

Run lint and test checks before opening a PR:

```bash
ruff check .
black src tests
pytest
```

## Testing

The project includes comprehensive test coverage with 120+ test cases across all core modules, including unit tests, integration tests, and E2E MCP server tests.

### Running Tests

```bash
# Run all unit tests (fast, no external dependencies)
pytest -m "not integration"

# Run all tests including integration tests
pytest

# Run tests with coverage reporting
pytest --cov=src/radarr_manager --cov-report=term-missing

# Run specific test modules
pytest tests/clients/test_radarr.py -v
pytest tests/services/test_sync.py -v
pytest tests/providers/test_openai.py -v
pytest tests/mcp/test_server.py -v

# Run MCP E2E integration tests
pytest tests/test_mcp_integration_e2e.py -v

# Quick verification of RadarrClient methods
python scripts/test_mcp_local.py
```

### Integration Tests

Integration tests are marked with `@pytest.mark.integration` and require live services:

```bash
# Run only integration tests (requires live Radarr + API keys)
pytest -m integration

# Skip integration tests (default behavior)
pytest -m "not integration"
```

**Integration test requirements:**
- `RADARR_API_KEY` and `RADARR_BASE_URL` for Radarr tests
- `OPENAI_API_KEY` for OpenAI provider tests

### Test Structure

- `tests/clients/` - HTTP client and API interaction tests (includes RadarrClient methods)
- `tests/services/` - Business logic and sync service tests
- `tests/providers/` - LLM provider and factory pattern tests
- `tests/config/` - Configuration loading and validation tests
- `tests/mcp/` - MCP server tool implementation tests
- `tests/fixtures/` - Shared test data and API response mocks
- `tests/test_integration.py` - End-to-end pipeline tests
- `tests/test_mcp_integration_e2e.py` - E2E MCP server integration tests
- `scripts/test_mcp_local.py` - Quick verification script for RadarrClient methods

### Writing Tests

Tests use:
- **pytest-asyncio** for async/await support
- **respx** for HTTP mocking
- **unittest.mock** for object mocking
- **pytest fixtures** for shared test setup

Example test structure:
```python
@pytest.mark.asyncio
async def test_example():
    # Setup mocks
    # Execute code under test
    # Assert expected behavior
```

## Troubleshooting

### Common Issues

**"Missing RADARR_BASE_URL or RADARR_API_KEY"**
- Ensure environment variables are set or configured in `.env`
- Check that `.env` is in the project root directory
- Verify Radarr API key is valid: `radarr-manager config --show-sources`

**"OpenAI request failed"**
- Verify `OPENAI_API_KEY` is set and valid
- Check your OpenAI account has sufficient credits
- Ensure selected model supports web search (gpt-4o-mini, gpt-4o, o1-mini)

**"No suggestions discovered"**
- OpenAI may not find trending movies at the moment
- Try running discovery again or use `--provider static` for testing
- Check OpenAI API status: https://status.openai.com/
- Try `--discovery-mode hybrid` for more reliable results
- Try `--discovery-mode smart_agentic` for highest quality mainstream movies

**"Scraper error" or "Crawl4AI connection failed"**
- Ensure Crawl4AI is running: `docker compose -f docker-compose.dev.yml up -d`
- Check Crawl4AI health: `curl http://localhost:11235/health`
- Access Crawl4AI dashboard: http://localhost:11235/dashboard
- Verify `SCRAPER_API_URL` points to correct endpoint

**Movies not being added to Radarr**
- Remove `--dry-run` flag to perform actual sync
- Check Radarr quality profiles: `radarr-manager config`
- Verify root folder path exists in Radarr
- Use `--force` to add potential duplicates

### Debug Mode

Enable verbose logging:
```bash
export LOG_LEVEL=DEBUG
radarr-manager discover --limit 1
```

### Configuration Validation

Check current settings:
```bash
radarr-manager config --show-sources
```

Test Radarr connection:
```bash
radarr-manager sync --dry-run --limit 1
```

## Security Notes

- **Never commit API keys** to version control
- Use `.env` files for local development (already in `.gitignore`)
- Store production secrets in environment variables or secure vaults
- Radarr API keys have full access to your media library

## Contributing

See `AGENTS.md` for detailed contributor guidelines and development practices.

### Quick Development Setup

```bash
git clone <repository>
cd radarr-manager
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env  # Configure with your API keys
pytest  # Run test suite
```

## License

[Add your license information here]
