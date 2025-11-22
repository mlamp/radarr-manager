# Radarr Manager

CLI toolkit for sourcing blockbuster releases via LLM providers and synchronizing them with a Radarr instance. The tool discovers trending theatrical movies, normalizes metadata, and optionally enqueues them in Radarr with consistent profiles and tags.

## Features

- 🎬 **Intelligent Movie Discovery**: Uses LLM providers (OpenAI) with web search for real-time box office trends
- 🔍 **Deep Analysis Mode (v1.6.0)**: Multi-source ratings validation with RT, IMDb, and Metacritic
  - Quality scoring with configurable thresholds
  - Red flag detection (poor ratings, low votes, score gaps)
  - Automated filtering of low-quality movies
- 🔄 **Safe Sync Operations**: Dry-run mode for validation before making changes
- ⚙️ **Flexible Configuration**: Environment variables, .env files, or TOML configuration
- 🏷️ **Smart Tagging**: Automatic tagging and quality profile assignment
- 🎯 **Oscar Winner Priority**: Prioritizes movies featuring Academy Award winners
- 🔍 **Duplicate Detection**: Prevents adding movies already in your Radarr library
- 🧪 **Comprehensive Testing**: 119+ test cases with integration test support

## Requirements

- Python 3.12+
- A running Radarr instance
- OpenAI API key (for movie discovery)

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
  --limit INTEGER     Maximum number of movies to return (default: 5)
  --provider TEXT     Override provider (openai, static)
  --help             Show this message and exit
```

#### `sync`
Synchronize discovered movies with Radarr:

```bash
radarr-manager sync [OPTIONS]

Options:
  --limit INTEGER              Number of suggestions to evaluate (default: 5)
  --dry-run / --no-dry-run    Preview without changes (default: --dry-run)
  --force / --no-force        Add even if duplicates detected (default: --no-force)
  --deep-analysis             Enable per-movie quality analysis (v1.6.0+)
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

The project includes comprehensive test coverage with 119+ test cases across all core modules.

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

- `tests/clients/` - HTTP client and API interaction tests
- `tests/services/` - Business logic and sync service tests
- `tests/providers/` - LLM provider and factory pattern tests
- `tests/config/` - Configuration loading and validation tests
- `tests/fixtures/` - Shared test data and API response mocks
- `tests/test_integration.py` - End-to-end pipeline tests

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
