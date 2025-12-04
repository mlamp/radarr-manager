# Docker Guide for Radarr Manager

Complete guide for running Radarr Manager in Docker containers.

## Table of Contents

- [Quick Start](#quick-start)
- [Available Images](#available-images)
- [Basic Usage](#basic-usage)
- [Advanced Configuration](#advanced-configuration)
- [Networking](#networking)
- [Docker Compose](#docker-compose)
- [Scheduling](#scheduling)
- [Troubleshooting](#troubleshooting)

## Quick Start

Pull the latest image and run a discovery:

```bash
docker pull mlamp/radarr-manager:latest

docker run --rm \
  -e RADARR_BASE_URL="http://your-radarr:7878" \
  -e RADARR_API_KEY="your-api-key" \
  -e OPENAI_API_KEY="your-openai-key" \
  mlamp/radarr-manager:latest \
  discover --limit 5
```

## Available Images

### Docker Hub

```bash
# Latest stable release
mlamp/radarr-manager:latest

# Specific version (note: no 'v' prefix in Docker tags)
mlamp/radarr-manager:1.12.0
mlamp/radarr-manager:1.11.0
mlamp/radarr-manager:1.9.0

# Older version tags
mlamp/radarr-manager:1.5.1
mlamp/radarr-manager:1.5.0
```

**Note:** Docker image tags use semantic versioning **without** the `v` prefix (e.g., `1.7.0`), while git tags include the `v` prefix (e.g., `v1.7.0`).

### Architecture Support

Multi-architecture images support:
- `linux/amd64` - Intel/AMD x86_64
- `linux/arm64` - ARM 64-bit (Apple Silicon, Raspberry Pi 4+)

Docker automatically pulls the correct architecture for your platform.

## Basic Usage

### Discover Movies

Find trending movies without modifying Radarr:

```bash
docker run --rm \
  -e OPENAI_API_KEY="sk-..." \
  -e RADARR_BASE_URL="http://192.168.1.100:7878" \
  -e RADARR_API_KEY="..." \
  mlamp/radarr-manager:latest \
  discover --limit 10
```

### Sync with Dry-Run (Safe Preview)

Preview what would be added without making changes:

```bash
docker run --rm \
  --env-file /path/to/.env \
  mlamp/radarr-manager:latest \
  sync --dry-run --limit 5
```

### Production Sync

Actually add movies to Radarr:

```bash
docker run --rm \
  --env-file /path/to/.env \
  --network host \
  mlamp/radarr-manager:latest \
  sync --limit 10 --no-dry-run
```

### Production Sync with Deep Analysis (Recommended)

Use multi-source ratings validation to filter out low-quality movies:

```bash
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:1.7.0 \
  sync --limit 10 --no-dry-run --deep-analysis --debug
```

**Deep Analysis Features (v1.6.0+):**
- Fetches RT critics/audience, IMDb, and Metacritic scores
- Calculates quality scores (0-10) with weighted ratings
- Detects red flags (poor ratings, low votes, score gaps)
- Filters out movies scoring < 6.0 or with > 2 red flags

### Smart Agentic Discovery (v1.12.0+)

Use the LLM orchestrator with specialized agents for highest quality mainstream movie discovery:

```bash
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:1.12.0 \
  sync --discovery-mode smart_agentic --limit 10 --no-dry-run --debug
```

**Smart Agentic Features (v1.12.0+):**
- GPT-4o orchestrator coordinates specialized agents
- Fetches from IMDB moviemeter (top 10/50/100 most popular)
- Web search for current box office and trending movies
- Intelligent validation and ranking with quality filtering
- Excludes low-quality content (concerts, anime compilations, re-releases)
- Prioritizes mainstream wide releases with IMDB 7.0+ ratings

### Manual Movie Addition with Quality Gate (v1.7.0+)

Add specific movies with intelligent quality filtering:

```bash
# Basic add with quality gate (enabled by default)
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:latest \
  add --title "Dune: Part Three" --year 2026 --no-dry-run
```

**Quality Gating Features:**
- Blocks movies below quality threshold (default: 5.0/10)
- Multi-source ratings: RT critics/audience, IMDb, Metacritic
- Override support with `--force` flag for guilty pleasures
- Detailed JSON output with quality scores and recommendations

**Examples:**

```bash
# Skip quality checks for fast add
docker run --rm \
  --env-file /path/to/.env \
  --network host \
  mlamp/radarr-manager:latest \
  add --title "The Batman Part II" --year 2026 --no-deep-analysis --no-dry-run

# Custom quality threshold (stricter filtering)
docker run --rm \
  --env-file /path/to/.env \
  mlamp/radarr-manager:latest \
  add --title "Borderline Movie" --year 2024 --quality-threshold 7.0

# Force add a low-quality movie (override quality gate)
docker run --rm \
  --env-file /path/to/.env \
  mlamp/radarr-manager:latest \
  add --title "Movie 43" --year 2013 --force --no-dry-run

# JSON output for bot integration (default)
docker run --rm \
  --env-file /path/to/.env \
  mlamp/radarr-manager:latest \
  add --title "Inception" --year 2010

# Human-readable output
docker run --rm \
  --env-file /path/to/.env \
  mlamp/radarr-manager:latest \
  add --title "Interstellar" --year 2014 --no-json
```

**JSON Response Example (Quality Rejection):**
```json
{
  "success": false,
  "error": "quality_too_low",
  "message": "Movie has poor ratings (score: 2.5/10, threshold: 5.0)",
  "quality_analysis": {
    "overall_score": 2.5,
    "threshold": 5.0,
    "passed": false,
    "recommendation": "NOT RECOMMENDED - Quality concerns, likely skip",
    "ratings": {
      "rotten_tomatoes": {"critics_score": 4, "audience_score": 18},
      "imdb": {"score": 4.3, "votes": 95420},
      "metacritic": {"score": 18}
    },
    "red_flags": [...]
  },
  "can_override": true,
  "override_instructions": "To add this movie anyway, use: radarr-manager add --title \"Movie 43\" --year 2013 --force"
}
```

**Integration with Starr Butler (Telegram Bot):**
```bash
# Telegram bot calls radarr-manager via Docker
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:latest \
  add --title "$MOVIE_TITLE" --year $YEAR --no-dry-run

# Parse JSON response
# Check exit code: 0=success, 1=not found, 2=duplicate, 3=quality too low
# Handle quality gate with --force flag if user confirms
```

### MCP Service Mode (v1.8.0+)

Run radarr-manager as a long-running MCP (Model Context Protocol) server for AI agent integration.

**Why MCP Service Mode?**
- Persistent service eliminates startup overhead
- Connection pooling for better performance
- Native tool API for AI agents (Telegram bots, Discord bots)
- Structured responses without parsing

**Start MCP Server:**

```bash
# Run as daemon service
docker run -d \
  --name radarr-manager-mcp \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  --restart unless-stopped \
  mlamp/radarr-manager:1.8.0 \
  serve --host 0.0.0.0 --debug

# Check logs
docker logs -f radarr-manager-mcp

# Stop service
docker stop radarr-manager-mcp
```

**Available MCP Tools:**
- `search_movie` - Check if movie exists in Radarr
- `add_movie` - Add with quality gating
- `analyze_quality` - Get quality analysis without adding
- `discover_movies` - Find blockbuster suggestions
- `sync_movies` - Discover and sync in one call

**Docker Compose MCP Service:**

```yaml
version: '3.8'

services:
  radarr-manager-mcp:
    image: mlamp/radarr-manager:1.8.0
    container_name: radarr-manager-mcp
    command: serve --host 0.0.0.0 --debug
    env_file: /mnt/user/appdata/radarr-manager/.env
    network_mode: host
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "pgrep", "-f", "radarr-manager"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Integration Example (Telegram Bot):**

Your Telegram bot connects to the MCP server and calls tools directly:

```python
from mcp import Client

# Connect to MCP server
mcp = Client("stdio://docker exec radarr-manager-mcp radarr-manager serve")

# Call add_movie tool
async def handle_movie_request(title: str, year: int):
    result = await mcp.call_tool("add_movie", {
        "title": title,
        "year": year,
        "dry_run": False,
        "quality_threshold": 5.0
    })

    if result["success"]:
        return f"✅ Added {title}!"
    elif result["error"] == "quality_too_low":
        return f"⚠️ Poor quality (score: {result['quality_analysis']['overall_score']}/10)"
    else:
        return f"❌ {result['message']}"
```

## Advanced Configuration

### Using Environment Files

Create a `.env` file with your configuration:

```bash
# .env
RADARR_BASE_URL=http://192.168.1.100:7878
RADARR_API_KEY=4d2c1061d52d40659fac04f26640136c
RADARR_QUALITY_PROFILE_ID=4
RADARR_ROOT_FOLDER_PATH=/movies
RADARR_MINIMUM_AVAILABILITY=inCinemas
RADARR_MONITOR=true
RADARR_TAGS=auto-boxoffice

OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
LLM_PROVIDER=openai
```

Run with the env file:

```bash
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:latest \
  sync --limit 5 --no-dry-run
```

### Inline Environment Variables

Pass environment variables directly:

```bash
docker run --rm \
  -e RADARR_BASE_URL="http://192.168.1.100:7878" \
  -e RADARR_API_KEY="your-key" \
  -e RADARR_QUALITY_PROFILE_ID=4 \
  -e RADARR_ROOT_FOLDER_PATH="/movies" \
  -e RADARR_TAGS="auto-discover" \
  -e OPENAI_API_KEY="sk-..." \
  -e OPENAI_MODEL="gpt-4o-mini" \
  mlamp/radarr-manager:latest \
  sync --limit 3
```

### Volume Mounting for Configuration

Mount a TOML config file:

```bash
docker run --rm \
  -v ~/.config/radarr-manager:/root/.config/radarr-manager:ro \
  mlamp/radarr-manager:latest \
  config --show-sources
```

## Networking

### Host Network Mode

Best for accessing Radarr on localhost or same machine:

```bash
docker run --rm \
  --network host \
  --env-file .env \
  mlamp/radarr-manager:latest \
  sync --limit 5
```

**Advantages:**
- Direct access to `localhost` and local network services
- No port mapping required
- Simplest configuration for same-host Radarr

**Use when:**
- Radarr is running on the same Docker host
- Radarr URL is `http://localhost:7878` or `http://127.0.0.1:7878`

### Bridge Network Mode (Default)

Standard Docker networking:

```bash
docker run --rm \
  -e RADARR_BASE_URL="http://192.168.1.100:7878" \
  --env-file .env \
  mlamp/radarr-manager:latest \
  sync --limit 5
```

**Use when:**
- Radarr is accessible via IP address
- Radarr is on another machine
- You need network isolation

### Custom Docker Networks

Join existing Docker network to access other containers:

```bash
# If Radarr is in a custom network called 'media'
docker run --rm \
  --network media \
  -e RADARR_BASE_URL="http://radarr:7878" \
  --env-file .env \
  mlamp/radarr-manager:latest \
  sync --limit 5
```

## Docker Compose

### Basic Setup

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  radarr-manager:
    image: mlamp/radarr-manager:latest
    env_file: .env
    command: sync --limit 5 --no-dry-run
    restart: unless-stopped
```

Run:
```bash
docker-compose run --rm radarr-manager
```

### With Deep Analysis

```yaml
version: '3.8'

services:
  radarr-manager:
    image: mlamp/radarr-manager:1.12.0
    network_mode: host
    env_file: /mnt/user/appdata/radarr-manager/.env
    command: sync --limit 10 --no-dry-run --deep-analysis --debug
    restart: unless-stopped
```

### With Smart Agentic Discovery (v1.12.0+)

```yaml
version: '3.8'

services:
  radarr-manager:
    image: mlamp/radarr-manager:1.12.0
    network_mode: host
    env_file: /mnt/user/appdata/radarr-manager/.env
    command: sync --discovery-mode smart_agentic --limit 10 --no-dry-run --debug
    restart: unless-stopped
```

### Complete Setup with Environment Variables

```yaml
version: '3.8'

services:
  radarr-manager:
    image: mlamp/radarr-manager:latest
    container_name: radarr-manager
    environment:
      # Radarr configuration
      - RADARR_BASE_URL=http://radarr:7878
      - RADARR_API_KEY=${RADARR_API_KEY}
      - RADARR_QUALITY_PROFILE_ID=4
      - RADARR_ROOT_FOLDER_PATH=/movies
      - RADARR_MINIMUM_AVAILABILITY=inCinemas
      - RADARR_MONITOR=true
      - RADARR_TAGS=auto-boxoffice

      # OpenAI configuration
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_MODEL=gpt-4o-mini
      - LLM_PROVIDER=openai

    networks:
      - media

    # Run on startup, then exit
    command: sync --limit 5 --no-dry-run
    restart: "no"

networks:
  media:
    external: true
```

### Discovery Only

```yaml
version: '3.8'

services:
  radarr-discovery:
    image: mlamp/radarr-manager:latest
    env_file: .env
    command: discover --limit 20
    restart: "no"
```

Run manually:
```bash
docker-compose run --rm radarr-discovery
```

## Scheduling

### Using Cron (Host Machine)

Add to your crontab (`crontab -e`):

```bash
# Run every day at 2 AM
0 2 * * * docker run --rm --env-file /path/to/.env --network host mlamp/radarr-manager:latest sync --limit 10 --no-dry-run --deep-analysis >> /var/log/radarr-manager.log 2>&1

# Run every 6 hours
0 */6 * * * docker run --rm --env-file /path/to/.env --network host mlamp/radarr-manager:latest sync --limit 5 --no-dry-run
```

### Using Systemd Timer

Create `/etc/systemd/system/radarr-manager.service`:

```ini
[Unit]
Description=Radarr Manager Sync
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/docker run --rm --env-file /mnt/user/appdata/radarr-manager/.env --network host mlamp/radarr-manager:latest sync --limit 10 --no-dry-run --deep-analysis
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/radarr-manager.timer`:

```ini
[Unit]
Description=Run Radarr Manager Daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable radarr-manager.timer
sudo systemctl start radarr-manager.timer
sudo systemctl status radarr-manager.timer
```

### Using Unraid User Scripts

If running on Unraid, create a custom script:

```bash
#!/bin/bash

docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:latest \
  sync --limit 10 --no-dry-run --deep-analysis --debug | \
  tee -a /mnt/user/appdata/radarr-manager/logs/sync-$(date +%Y%m%d).log
```

Schedule via Unraid's User Scripts plugin.

## Troubleshooting

### Check Container Logs

```bash
# Run with verbose output
docker run --rm \
  --env-file .env \
  mlamp/radarr-manager:latest \
  sync --limit 1 --debug
```

### Verify Configuration

```bash
docker run --rm \
  --env-file .env \
  mlamp/radarr-manager:latest \
  config --show-sources
```

### Test Network Connectivity

```bash
# Test if Radarr is reachable
docker run --rm \
  --network host \
  --env-file .env \
  mlamp/radarr-manager:latest \
  sync --dry-run --limit 1
```

### Common Issues

**"Connection refused" to Radarr:**
- Use `--network host` if Radarr is on `localhost`
- Check `RADARR_BASE_URL` points to correct IP/hostname
- Verify Radarr is running and accessible

**"No ratings available" with Deep Analysis:**
- Some movies (especially unreleased) may not have RT/Metacritic scores yet
- This is expected for upcoming releases
- Deep analysis will still evaluate based on available data

**API key errors:**
- Verify `RADARR_API_KEY` is correct
- Check `OPENAI_API_KEY` is valid and has credits
- Use `docker run` with `--debug` flag to see detailed errors

### Interactive Shell

Debug inside the container:

```bash
docker run --rm -it \
  --env-file .env \
  --entrypoint /bin/bash \
  mlamp/radarr-manager:latest

# Inside container:
radarr-manager config
radarr-manager discover --limit 1
```

## Building from Source

Build your own image:

```bash
# Clone the repository
git clone https://github.com/mlamp/radarr-manager.git
cd radarr-manager

# Build locally
docker build -t radarr-manager:local .

# Run your local build
docker run --rm --env-file .env radarr-manager:local discover
```

Build multi-architecture image:

```bash
# Create builder
docker buildx create --name multiarch --use

# Build for multiple platforms
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t yourusername/radarr-manager:custom \
  --push \
  .
```

## Best Practices

1. **Use Deep Analysis for Production** (v1.6.0+)
   ```bash
   sync --limit 10 --no-dry-run --deep-analysis
   ```

2. **Always Test with Dry-Run First**
   ```bash
   sync --dry-run --limit 5
   ```

3. **Store .env Files Securely**
   - Never commit API keys to version control
   - Use restrictive permissions: `chmod 600 .env`

4. **Use Specific Version Tags**
   - Pin to specific versions in production
   - Test new versions before updating

5. **Enable Debug Output for Troubleshooting**
   ```bash
   sync --debug --limit 1
   ```

6. **Schedule Regular Syncs**
   - Daily or weekly syncs work well
   - Use `--limit` to control volume

## Examples

### Unraid Setup

```bash
# With deep analysis
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:1.12.0 \
  sync --limit 10 --no-dry-run --deep-analysis --debug

# With smart agentic discovery (recommended for highest quality)
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:1.12.0 \
  sync --discovery-mode smart_agentic --limit 10 --no-dry-run --debug
```

### Synology NAS

```bash
docker run --rm \
  -e RADARR_BASE_URL="http://192.168.1.100:7878" \
  -e RADARR_API_KEY="your-key" \
  -e OPENAI_API_KEY="sk-..." \
  mlamp/radarr-manager:latest \
  sync --limit 5 --no-dry-run
```

### Kubernetes (Basic)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: radarr-manager
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: radarr-manager
            image: mlamp/radarr-manager:latest
            args: ["sync", "--limit", "10", "--no-dry-run", "--deep-analysis"]
            envFrom:
            - secretRef:
                name: radarr-manager-secrets
          restartPolicy: OnFailure
```

## Additional Resources

- [Main README](README.md) - General documentation
- [GitHub Repository](https://github.com/mlamp/radarr-manager)
- [Docker Hub](https://hub.docker.com/r/mlamp/radarr-manager)
- [Release Notes](https://github.com/mlamp/radarr-manager/releases)
