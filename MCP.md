# MCP Integration Guide

Complete guide for integrating radarr-manager with AI agents via Model Context Protocol (MCP).

## Table of Contents

- [Overview](#overview)
- [Why MCP?](#why-mcp)
- [Quick Start](#quick-start)
- [Available Tools](#available-tools)
- [Client Integration](#client-integration)
- [Response Schemas](#response-schemas)
- [Error Handling](#error-handling)
- [Use Cases](#use-cases)
- [Troubleshooting](#troubleshooting)

## Overview

MCP (Model Context Protocol) mode runs radarr-manager as a long-running service that exposes structured tools for AI agents. Perfect for:

- 🤖 **Telegram Bots** - Voice-to-movie automation (Starr Butler)
- 💬 **Discord Bots** - Server movie management
- 🌐 **Web Apps** - LLM-powered movie recommendations
- 🔧 **Custom Agents** - Any AI application needing Radarr integration

## Why MCP?

### CLI Approach (Subprocess Hell)

```python
# Every request spawns new process
result = subprocess.run(['docker', 'run', 'radarr-manager', 'add', ...])
# Parse JSON strings, check exit codes
data = json.loads(result.stdout)
if result.returncode == 3:
    # Quality gate logic...
```

**Problems:**
- ❌ 200-500ms startup overhead per request
- ❌ No connection pooling
- ❌ String parsing hell
- ❌ No type safety
- ❌ Docker overhead

### MCP Approach (Clean & Fast)

```python
# Persistent service, structured API
result = await mcp.call_tool("add_movie", {
    "title": "Dune: Part Three",
    "year": 2026
})
# Structured response, type-safe
if result["error"] == "quality_too_low":
    score = result["quality_analysis"]["overall_score"]
```

**Benefits:**
- ✅ ~10-100x faster (no startup overhead)
- ✅ Connection pooling, caching
- ✅ Type-safe structured responses
- ✅ Native AI agent integration
- ✅ Single service for all clients

## Quick Start

### Start MCP Server

```bash
# Local development
radarr-manager serve

# Production (network accessible)
radarr-manager serve --host 0.0.0.0 --port 8080 --debug

# Docker
docker run -d \
  --name radarr-manager-mcp \
  --env-file .env \
  --network host \
  mlamp/radarr-manager:1.8.0 \
  serve --host 0.0.0.0 --debug
```

### Python Client

```bash
pip install mcp
```

```python
from mcp import Client

async def main():
    async with Client("stdio://radarr-manager serve") as mcp:
        # Check if movie exists
        result = await mcp.call_tool("search_movie", {
            "title": "Inception",
            "year": 2010
        })
        print(result["exists"])  # True/False
```

## Available Tools

### 1. search_movie

Check if a movie already exists in Radarr.

**Parameters:**
```python
{
    "title": str,        # Required: Movie title
    "year": int | None   # Optional: Release year
}
```

**Response:**
```json
{
    "exists": true,
    "movie": {
        "title": "Inception",
        "year": 2010,
        "tmdbId": 27205,
        "hasFile": true,
        "monitored": true
    },
    "message": "✓ Inception is already in Radarr"
}
```

**Use Case:**
```python
# Telegram bot: "Do we have Inception?"
result = await mcp.call_tool("search_movie", {
    "title": "Inception",
    "year": 2010
})

if result["exists"]:
    movie = result["movie"]
    status = "Downloaded" if movie["hasFile"] else "Downloading"
    return f"✅ Yes! Status: {status}"
else:
    return "❌ Not in library. Want me to add it?"
```

### 2. add_movie

Add movie to Radarr with intelligent quality gating.

**Parameters:**
```python
{
    "title": str | None,              # Movie title
    "year": int | None,               # Release year
    "tmdb_id": int | None,            # TMDB ID (e.g., 27205)
    "imdb_id": str | None,            # IMDB ID (e.g., "tt1375666")
    "force": bool,                    # Default: False - Bypass quality gate
    "deep_analysis": bool,            # Default: True - Enable quality checks
    "quality_threshold": float,       # Default: 5.0 - Min score (0-10)
    "dry_run": bool                   # Default: True - Preview only
}
```

**At least one identifier required:** `title`, `tmdb_id`, or `imdb_id`

**Success Response:**
```json
{
    "success": true,
    "message": "Added: Dune: Part Three (2026)",
    "movie": {
        "title": "Dune: Part Three",
        "year": 2026,
        "tmdb_id": 123456
    },
    "quality_analysis": {
        "overall_score": 8.5,
        "threshold": 5.0,
        "passed": true,
        "recommendation": "HIGHLY RECOMMENDED",
        "ratings": {
            "rotten_tomatoes": {
                "critics_score": 85,
                "audience_score": 90
            },
            "imdb": {
                "score": 8.3,
                "votes": 250000
            },
            "metacritic": {
                "score": 78
            }
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
    "message": "Movie has poor ratings (score: 2.5/10, threshold: 5.0)",
    "movie": {
        "title": "Movie 43",
        "year": 2013,
        "tmdb_id": 93456
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
            "RT critics score very poor (4%)",
            "Large RT score gap (critics: 4% vs audience: 18%)",
            "Metacritic score very poor (18/100)"
        ]
    },
    "can_override": true,
    "override_instructions": "To add anyway, call add_movie again with force=true"
}
```

**Use Case:**
```python
# Telegram bot: User says "Add Dune Part 3"
result = await mcp.call_tool("add_movie", {
    "title": "Dune: Part Three",
    "year": 2026,
    "dry_run": False
})

if result["success"]:
    return f"✅ Added {result['movie']['title']}!"

elif result["error"] == "quality_too_low":
    qa = result["quality_analysis"]
    return (
        f"⚠️ {result['movie']['title']} has poor ratings:\n"
        f"Score: {qa['overall_score']}/10\n"
        f"RT: {qa['ratings']['rotten_tomatoes']['critics_score']}%\n\n"
        f"Add anyway? Reply 'yes force' to override."
    )

elif result["error"] == "already_exists":
    return f"✓ Already have {result['movie']['title']}!"
```

### 3. analyze_quality

Get quality analysis without adding the movie.

**Parameters:**
```python
{
    "title": str,        # Required: Movie title
    "year": int | None,  # Optional: Release year
    "tmdb_id": int | None  # Optional: TMDB ID
}
```

**Response:**
```json
{
    "overall_score": 7.8,
    "threshold": null,
    "passed": true,
    "recommendation": "RECOMMENDED - Good quality, worth adding",
    "ratings": {
        "rotten_tomatoes": {
            "critics_score": 82,
            "audience_score": 87
        },
        "imdb": {
            "score": 7.9,
            "votes": 180000
        },
        "metacritic": {
            "score": 74
        }
    },
    "red_flags": []
}
```

**Use Case:**
```python
# User asks: "Is Borderlands any good?"
result = await mcp.call_tool("analyze_quality", {
    "title": "Borderlands",
    "year": 2024
})

score = result["overall_score"]
rec = result["recommendation"]

return f"Score: {score}/10\n{rec}"
```

### 4. discover_movies

Discover trending blockbuster movies using AI.

**Parameters:**
```python
{
    "limit": int,        # Default: 10, Range: 1-50
    "region": str | None # Optional: Region code (e.g., "US")
}
```

**Response:**
```json
{
    "success": true,
    "movies": [
        {
            "title": "Dune: Part Three",
            "year": 2026,
            "tmdb_id": 123456,
            "imdb_id": "tt15239678",
            "reason": "Highly anticipated sequel to critically acclaimed Dune series",
            "quality_score": null
        }
    ],
    "count": 10,
    "message": "Discovered 10 blockbuster movies"
}
```

**Use Case:**
```python
# User: "What's trending?"
result = await mcp.call_tool("discover_movies", {"limit": 5})

movies = "\n".join([
    f"• {m['title']} ({m['year']}) - {m['reason']}"
    for m in result["movies"]
])

return f"🎬 Trending Movies:\n{movies}"
```

### 5. sync_movies

Discover and sync movies to Radarr in one operation.

**Parameters:**
```python
{
    "limit": int,           # Default: 10, Range: 1-50
    "dry_run": bool,        # Default: True - Preview only
    "deep_analysis": bool   # Default: True - Enable quality filtering
}
```

**Response:**
```json
{
    "success": true,
    "results": [
        {
            "title": "Gladiator II",
            "year": 2024,
            "status": "added",
            "reason": "Successfully added to Radarr",
            "quality_score": 8.2
        },
        {
            "title": "Movie 43",
            "year": 2013,
            "status": "skipped",
            "reason": "Skipped due to quality threshold",
            "quality_score": 2.5
        },
        {
            "title": "Inception",
            "year": 2010,
            "status": "exists",
            "reason": "Already in Radarr",
            "quality_score": null
        }
    ],
    "summary": {
        "added": 1,
        "existing": 1,
        "skipped": 1,
        "queued": 3
    },
    "message": "Synced 3 movies (added: 1, exists: 1, skipped: 1)"
}
```

**Use Case:**
```python
# Scheduled job: Daily discovery
result = await mcp.call_tool("sync_movies", {
    "limit": 20,
    "dry_run": False,
    "deep_analysis": True
})

summary = result["summary"]
return (
    f"Daily sync complete:\n"
    f"✅ Added: {summary['added']}\n"
    f"⏭️ Skipped: {summary['skipped']}\n"
    f"✓ Existing: {summary['existing']}"
)
```

## Client Integration

### Telegram Bot (Starr Butler)

```python
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from mcp import Client
import openai

# Initialize MCP client
mcp_client = Client("stdio://docker exec radarr-manager-mcp radarr-manager serve")

async def handle_voice(update: Update, context):
    """Handle voice messages - transcribe and process movie requests."""
    # 1. Download voice message
    voice = await update.message.voice.get_file()
    audio_bytes = await voice.download_as_bytearray()

    # 2. Transcribe with Whisper
    transcript = await openai.audio.transcribe(
        model="whisper-1",
        file=audio_bytes
    )
    text = transcript["text"]

    # 3. Parse movie request with GPT
    parsed = await openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": (
                "Extract movie title and year from user request. "
                "Return JSON: {\"title\": \"...\", \"year\": 2024}"
            )
        }, {
            "role": "user",
            "content": text
        }],
        response_format={"type": "json_object"}
    )

    movie_request = json.loads(parsed.choices[0].message.content)

    # 4. Check if exists
    search_result = await mcp_client.call_tool("search_movie", movie_request)

    if search_result["exists"]:
        await update.message.reply_text(
            f"✅ We already have {movie_request['title']}!"
        )
        return

    # 5. Add with quality gate
    add_result = await mcp_client.call_tool("add_movie", {
        **movie_request,
        "dry_run": False
    })

    if add_result["success"]:
        await update.message.reply_text(
            f"✅ Added {movie_request['title']} to Radarr!"
        )

    elif add_result["error"] == "quality_too_low":
        qa = add_result["quality_analysis"]

        # Store in context for follow-up
        context.user_data["pending_movie"] = movie_request

        await update.message.reply_text(
            f"⚠️ {movie_request['title']} has poor ratings:\n\n"
            f"📊 Score: {qa['overall_score']}/10\n"
            f"🍅 RT: {qa['ratings']['rotten_tomatoes']['critics_score']}%\n"
            f"⭐ IMDb: {qa['ratings']['imdb']['score']}/10\n\n"
            f"Red flags:\n" + "\n".join(f"• {flag}" for flag in qa['red_flags']) + "\n\n"
            f"Still want to add it? Reply 'yes' to confirm."
        )

    elif add_result["error"] == "not_found":
        await update.message.reply_text(
            f"❌ Couldn't find '{movie_request['title']}' in TMDB. "
            f"Try a different title or year?"
        )

async def handle_confirmation(update: Update, context):
    """Handle user confirmations for quality gate overrides."""
    text = update.message.text.lower()

    if text in ["yes", "add it", "add anyway"]:
        pending = context.user_data.get("pending_movie")

        if not pending:
            await update.message.reply_text("Nothing pending to add.")
            return

        # Force add
        result = await mcp_client.call_tool("add_movie", {
            **pending,
            "force": True,
            "dry_run": False
        })

        if result["success"]:
            await update.message.reply_text(
                f"✅ Added {pending['title']} (quality gate overridden)"
            )
            context.user_data.pop("pending_movie")
        else:
            await update.message.reply_text(
                f"❌ Failed to add: {result['message']}"
            )

async def handle_trending(update: Update, context):
    """Show trending movies."""
    result = await mcp_client.call_tool("discover_movies", {"limit": 5})

    movies = "\n\n".join([
        f"🎬 {m['title']} ({m['year']})\n{m['reason']}"
        for m in result["movies"]
    ])

    await update.message.reply_text(
        f"🔥 Trending Movies:\n\n{movies}"
    )

# Setup bot
app = Application.builder().token(TELEGRAM_TOKEN).build()

app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation))
app.add_handler(CommandHandler("trending", handle_trending))

app.run_polling()
```

### Discord Bot

```python
import discord
from discord.ext import commands
from mcp import Client

bot = commands.Bot(command_prefix="!")
mcp = Client("stdio://radarr-manager serve")

@bot.command()
async def movie(ctx, *, query: str):
    """Add a movie to Radarr."""
    # Parse query (simple example)
    parts = query.rsplit(" ", 1)
    title = parts[0]
    year = int(parts[1]) if len(parts) > 1 else None

    result = await mcp.call_tool("add_movie", {
        "title": title,
        "year": year,
        "dry_run": False
    })

    if result["success"]:
        embed = discord.Embed(
            title=f"✅ Added {result['movie']['title']}",
            color=discord.Color.green()
        )

        if result["quality_analysis"]:
            qa = result["quality_analysis"]
            embed.add_field(
                name="Quality Score",
                value=f"{qa['overall_score']}/10",
                inline=True
            )
            embed.add_field(
                name="RT Critics",
                value=f"{qa['ratings']['rotten_tomatoes']['critics_score']}%",
                inline=True
            )

        await ctx.send(embed=embed)

    elif result["error"] == "quality_too_low":
        qa = result["quality_analysis"]

        embed = discord.Embed(
            title=f"⚠️ Quality Gate: {result['movie']['title']}",
            description=f"Score: {qa['overall_score']}/10 (threshold: {qa['threshold']})",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Red Flags",
            value="\n".join(qa['red_flags']) or "None",
            inline=False
        )

        embed.set_footer(text=result["override_instructions"])

        await ctx.send(embed=embed)

@bot.command()
async def trending(ctx):
    """Show trending movies."""
    result = await mcp.call_tool("discover_movies", {"limit": 10})

    embed = discord.Embed(
        title="🔥 Trending Movies",
        color=discord.Color.blue()
    )

    for movie in result["movies"][:5]:
        embed.add_field(
            name=f"{movie['title']} ({movie['year']})",
            value=movie['reason'],
            inline=False
        )

    await ctx.send(embed=embed)

bot.run(DISCORD_TOKEN)
```

### Web App (FastAPI + LLM)

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mcp import Client
import openai

app = FastAPI()
mcp = Client("stdio://radarr-manager serve")

class MovieRequest(BaseModel):
    query: str  # Natural language query

@app.post("/api/movies/add")
async def add_movie_natural_language(request: MovieRequest):
    """Add movie from natural language query."""
    # Parse with GPT
    parsed = await openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "Extract movie title and year. Return JSON."
        }, {
            "role": "user",
            "content": request.query
        }],
        response_format={"type": "json_object"}
    )

    movie_data = json.loads(parsed.choices[0].message.content)

    # Call MCP tool
    result = await mcp.call_tool("add_movie", {
        **movie_data,
        "dry_run": False
    })

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )

    return result

@app.get("/api/movies/trending")
async def get_trending():
    """Get trending movies."""
    result = await mcp.call_tool("discover_movies", {"limit": 20})
    return result["movies"]

@app.get("/api/movies/search/{title}")
async def search_movie(title: str, year: int | None = None):
    """Check if movie exists in Radarr."""
    result = await mcp.call_tool("search_movie", {
        "title": title,
        "year": year
    })
    return result
```

## Response Schemas

All MCP tools return structured JSON responses. See `src/radarr_manager/mcp/schemas.py` for complete Pydantic models.

### Common Error Codes

| Error | Description | Override? |
|-------|-------------|-----------|
| `not_found` | Movie not found in TMDB | ❌ No |
| `already_exists` | Movie already in Radarr | ❌ No |
| `quality_too_low` | Failed quality gate | ✅ Yes (`force=true`) |
| `add_failed` | Radarr API error | ❌ No |
| `missing_identifier` | No title/TMDB ID/IMDB ID provided | ❌ No |

## Error Handling

```python
async def safe_add_movie(title: str, year: int):
    """Add movie with comprehensive error handling."""
    try:
        result = await mcp.call_tool("add_movie", {
            "title": title,
            "year": year,
            "dry_run": False
        })

        if result["success"]:
            return {"status": "added", "movie": result["movie"]}

        error = result.get("error")

        if error == "quality_too_low":
            return {
                "status": "rejected",
                "reason": "poor_quality",
                "score": result["quality_analysis"]["overall_score"],
                "can_override": True
            }

        elif error == "already_exists":
            return {
                "status": "exists",
                "movie": result["movie"]
            }

        elif error == "not_found":
            return {
                "status": "not_found",
                "suggestion": "Try different title/year"
            }

        else:
            return {
                "status": "error",
                "message": result["message"]
            }

    except Exception as exc:
        logger.error(f"MCP error: {exc}")
        return {
            "status": "error",
            "message": "Service unavailable"
        }
```

## Use Cases

### 1. Voice-Controlled Movie Management

**Starr Butler** - Telegram bot with voice messages:
```
User: 🎤 "Add Dune Part 3"
Bot:  ✅ Added Dune: Part Three (2026)!
      📊 Score: 8.5/10 - Highly Recommended
```

### 2. Automated Quality Filtering

```python
# Nightly sync with quality filtering
async def nightly_sync():
    result = await mcp.call_tool("sync_movies", {
        "limit": 30,
        "dry_run": False,
        "deep_analysis": True
    })

    # Email report
    send_email(f"""
    Daily Radarr Sync Report

    ✅ Added: {result['summary']['added']}
    ⏭️ Skipped (poor quality): {result['summary']['skipped']}
    ✓ Already have: {result['summary']['existing']}
    """)
```

### 3. Conversational Movie Recommendations

```python
# ChatGPT-style conversation
user_msg = "I want to watch a sci-fi thriller like Inception"

# Get recommendations from LLM
recommendations = await get_llm_recommendations(user_msg)

# Check which ones we have
for movie in recommendations:
    result = await mcp.call_tool("search_movie", movie)

    if result["exists"]:
        print(f"✅ {movie['title']} - Ready to watch!")
    else:
        # Analyze quality before suggesting
        qa = await mcp.call_tool("analyze_quality", movie)

        if qa["overall_score"] >= 7.0:
            print(f"⭐ {movie['title']} - Want me to add it? (Score: {qa['overall_score']}/10)")
```

### 4. Multi-Platform Sync

```python
# Sync across Discord, Telegram, web app
class MovieService:
    def __init__(self):
        self.mcp = Client("stdio://radarr-manager serve")

    async def add_movie_request(self, platform: str, user_id: str, movie: dict):
        """Unified movie addition across platforms."""
        result = await self.mcp.call_tool("add_movie", {
            **movie,
            "dry_run": False
        })

        # Log to database
        await log_request(platform, user_id, movie, result)

        # Send notification to all platforms
        await notify_all_platforms(
            f"{user_id} added {movie['title']} via {platform}"
        )

        return result

# Usage
service = MovieService()

# Discord
await service.add_movie_request("discord", user_id, movie_data)

# Telegram
await service.add_movie_request("telegram", user_id, movie_data)

# Web
await service.add_movie_request("web", user_id, movie_data)
```

## Troubleshooting

### MCP Server Won't Start

```bash
# Check if already running
ps aux | grep "radarr-manager serve"

# Check logs
docker logs radarr-manager-mcp

# Verify environment variables
radarr-manager config

# Test connection
curl http://localhost:8080/health  # if HTTP endpoint exists
```

### Tool Calls Timeout

```python
# Increase timeout
mcp = Client("stdio://radarr-manager serve", timeout=30)

# Or check server load
docker stats radarr-manager-mcp
```

### Quality Analysis Missing

Check that OpenAI API key is configured:
```bash
docker exec radarr-manager-mcp env | grep OPENAI
```

### Connection Refused

```bash
# Check network mode
docker inspect radarr-manager-mcp | grep NetworkMode

# Verify host binding
netstat -tulpn | grep 8080
```

## Best Practices

1. **Connection Pooling**: Reuse MCP client instance
   ```python
   # Good - Single client
   mcp = Client("stdio://radarr-manager serve")

   # Bad - New client per request
   async def add_movie(...):
       mcp = Client(...)  # Don't do this!
   ```

2. **Error Handling**: Always wrap MCP calls in try/except
   ```python
   try:
       result = await mcp.call_tool(...)
   except Exception as exc:
       logger.error(f"MCP error: {exc}")
       return fallback_response()
   ```

3. **Quality Gates**: Use `deep_analysis` for automated additions
   ```python
   # User-initiated: Skip analysis for speed
   await mcp.call_tool("add_movie", {
       "title": title,
       "deep_analysis": False  # Fast add
   })

   # Automated sync: Enable quality filtering
   await mcp.call_tool("sync_movies", {
       "deep_analysis": True  # Filter junk
   })
   ```

4. **Rate Limiting**: Respect Radarr API limits
   ```python
   import asyncio
   from collections import deque

   class RateLimitedMCP:
       def __init__(self):
           self.mcp = Client("stdio://radarr-manager serve")
           self.requests = deque(maxlen=10)

       async def call_tool(self, name, args):
           # Max 10 requests per minute
           if len(self.requests) >= 10:
               oldest = self.requests[0]
               wait = 60 - (time.time() - oldest)
               if wait > 0:
                   await asyncio.sleep(wait)

           self.requests.append(time.time())
           return await self.mcp.call_tool(name, args)
   ```

5. **Dry Run First**: Preview before actual changes
   ```python
   # Preview
   preview = await mcp.call_tool("add_movie", {
       "title": title,
       "dry_run": True  # Safe preview
   })

   if preview["success"]:
       # User confirms
       actual = await mcp.call_tool("add_movie", {
           "title": title,
           "dry_run": False  # Execute
       })
   ```

## Additional Resources

- [Main README](README.md) - General documentation
- [Docker Guide](DOCKER.md) - Deployment and containers
- [GitHub Repository](https://github.com/mlamp/radarr-manager)
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Release Notes](https://github.com/mlamp/radarr-manager/releases)
