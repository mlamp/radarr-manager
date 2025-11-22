# Starr Butler

## Project Overview

A Telegram bot service that accepts voice messages from users, converts speech to text, intelligently detects media types (movies, TV shows, music), and automatically adds them to the appropriate *arr media server (Radarr, Sonarr, Lidarr). This service acts as a unified voice interface for managing your entire media library across all platforms.

## Purpose & Goals

### Primary Objective
Enable hands-free media library management through natural voice commands via Telegram, making it easy to add movies, TV shows, music, and books to your collection while on the go or during conversations.

### What This Achieves
- **Universal Media Interface**: One bot for all your *arr services (Radarr, Sonarr, Lidarr, Readarr)
- **Voice-First Experience**: Say "Add Dune Part 3" or "Add Stranger Things season 6" instead of typing
- **Intelligent Routing**: Automatically detects media type and routes to correct *arr service
- **Accessibility**: Add media from anywhere using Telegram on phone/desktop
- **Natural Language**: Request media conversationally without rigid syntax
- **Quality Control**: Optional integration with radarr-manager's deep analysis for movie quality filtering

## Use Cases

1. **Casual Discovery**: Hear about a movie or show in conversation, send voice message immediately
2. **Multi-Person Household**: Family members request media via shared Telegram bot
3. **Mobile First**: Add content while commuting, traveling, or away from computer
4. **Voice Notes**: "Hey bot, add The Batman 2, add Stranger Things season 6, add the new Kendrick album"
5. **Unified Management**: Single interface for all media types instead of multiple web UIs

## Architecture

### High-Level Flow

```
User (Voice Message)
    ↓
Telegram Bot Service
    ↓
Speech-to-Text (OpenAI Whisper API)
    ↓
Media Type Detection (LLM classification)
    ↓
Router:
    ├── Movie    → Radarr API
    ├── TV Show  → Sonarr API
    ├── Music    → Lidarr API (future)
    └── Book     → Readarr API (future)
    ↓
Confirmation to User
```

### Components

#### 1. Telegram Bot Service (New Project)
- Python-based Telegram bot using `python-telegram-bot` library
- Listens for voice messages and text commands
- Handles user authentication/authorization
- Manages conversation state and confirmations

#### 2. Speech-to-Text Module
- OpenAI Whisper API for voice transcription
- Supports multiple languages
- Handles background noise and audio quality variations

#### 3. Media Parser & Router Module
- LLM-based parsing (OpenAI GPT-4o-mini) to extract:
  - Media type (movie, tv_show, music, book)
  - Title
  - Release year / season number
  - Artist/author (for music/books)
- Handles natural language variations:
  - "Add Dune 3" → Movie
  - "Add Stranger Things season 6" → TV Show
  - "Add the new Kendrick album" → Music
  - "Add Project Hail Mary by Andy Weir" → Book

#### 4. *arr Integration Layer
- Direct API calls to Radarr/Sonarr/Lidarr/Readarr
- TMDB/TVDB/MusicBrainz lookups for metadata
- Handles quality profiles, root folders, and tags per service
- Returns status/confirmation to user

#### 5. Optional: radarr-manager Integration
- For movies: can use radarr-manager's deep analysis feature
- Provides quality filtering for movie additions
- Leverages existing discovery infrastructure

## Features

### Phase 1 (MVP) - Movies & TV Shows
- ✅ Accept voice messages in Telegram
- ✅ Convert speech to text using Whisper API
- ✅ Detect media type (movie vs TV show)
- ✅ Parse movie title/year or TV show title/season
- ✅ Add movies to Radarr
- ✅ Add TV shows to Sonarr
- ✅ Confirmation message back to user
- ✅ Basic error handling (not found, API errors)

### Phase 2 (Enhanced)
- 🔄 Text message support (direct typing)
- 🔄 Batch requests ("Add Dune 3, Stranger Things S6, and the new Beatles album")
- 🔄 Confirmation prompts with media details before adding
- 🔄 User preferences per media type (quality profiles, folders)
- 🔄 Search results display (multiple matches)
- 🔄 Music support (Lidarr integration)
- 🔄 Book support (Readarr integration)

### Phase 3 (Advanced)
- 🔄 Integration with radarr-manager's deep analysis for movies
- 🔄 Quality score preview before adding
- 🔄 Multi-user support with permissions
- 🔄 Statistics and library insights ("What's in my library?")
- 🔄 Scheduled discovery ("Find 5 new movies every Sunday")
- 🔄 Watch status tracking
- 🔄 Plex/Jellyfin integration ("What's available to watch now?")

## Technical Stack

### Core Technologies
```yaml
Language: Python 3.12+
Bot Framework: python-telegram-bot (v20+)
Speech-to-Text: OpenAI Whisper API
NLP/Parsing: OpenAI GPT-4o-mini
Container: Docker + Docker Compose
Integration: Radarr/Sonarr/Lidarr APIs
Optional: radarr-manager Docker image (for movie quality analysis)
```

### Key Dependencies
```python
python-telegram-bot>=20.0  # Telegram bot API
openai>=1.44                # Whisper + GPT for parsing
httpx>=0.27                 # HTTP client for *arr APIs
pydantic>=2.7               # Data validation
python-dotenv>=1.0          # Configuration
tenacity>=9.0               # Retry logic
```

## *arr Service Integration

### Supported Services

#### Radarr (Movies) - Phase 1
```python
POST /api/v3/movie
{
  "title": "Dune: Part Three",
  "year": 2026,
  "tmdbId": 12345,
  "qualityProfileId": 4,
  "rootFolderPath": "/movies",
  "monitored": true,
  "addOptions": {"searchForMovie": true}
}
```

#### Sonarr (TV Shows) - Phase 1
```python
POST /api/v3/series
{
  "title": "Stranger Things",
  "tvdbId": 305288,
  "qualityProfileId": 4,
  "rootFolderPath": "/tv",
  "seasonFolder": true,
  "monitored": true,
  "addOptions": {
    "searchForMissingEpisodes": true,
    "monitor": "future"  # or "all", "latest", "first"
  }
}
```

#### Lidarr (Music) - Phase 2
```python
POST /api/v1/artist
{
  "artistName": "Kendrick Lamar",
  "foreignArtistId": "musicbrainz-id",
  "qualityProfileId": 1,
  "rootFolderPath": "/music",
  "monitored": true
}
```

#### Readarr (Books) - Phase 3
```python
POST /api/v1/author
{
  "authorName": "Andy Weir",
  "foreignAuthorId": "goodreads-id",
  "qualityProfileId": 1,
  "rootFolderPath": "/books",
  "monitored": true
}
```

### Optional: radarr-manager Integration

For movies with quality filtering:
```bash
# Instead of calling Radarr directly, use radarr-manager
docker run --rm \
  --env-file /mnt/user/appdata/radarr-manager/.env \
  --network host \
  mlamp/radarr-manager:latest \
  add --title "Movie Title" --year 2026 --deep-analysis
```

## Configuration

### Environment Variables
```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ALLOWED_USERS=123456789,987654321  # User ID whitelist

# OpenAI (Whisper + Parsing)
OPENAI_API_KEY=sk-proj-...
OPENAI_WHISPER_MODEL=whisper-1
OPENAI_PARSER_MODEL=gpt-4o-mini

# Radarr (Movies)
RADARR_BASE_URL=http://localhost:7878
RADARR_API_KEY=your-radarr-api-key
RADARR_QUALITY_PROFILE_ID=4
RADARR_ROOT_FOLDER_PATH=/movies

# Sonarr (TV Shows)
SONARR_BASE_URL=http://localhost:8989
SONARR_API_KEY=your-sonarr-api-key
SONARR_QUALITY_PROFILE_ID=4
SONARR_ROOT_FOLDER_PATH=/tv
SONARR_SEASON_MONITORING=future  # all, future, latest, first

# Lidarr (Music) - Optional
LIDARR_BASE_URL=http://localhost:8686
LIDARR_API_KEY=your-lidarr-api-key
LIDARR_QUALITY_PROFILE_ID=1
LIDARR_ROOT_FOLDER_PATH=/music

# Readarr (Books) - Optional
READARR_BASE_URL=http://localhost:8787
READARR_API_KEY=your-readarr-api-key
READARR_QUALITY_PROFILE_ID=1
READARR_ROOT_FOLDER_PATH=/books

# Optional: radarr-manager Integration
RADARR_MANAGER_ENABLED=true
RADARR_MANAGER_IMAGE=mlamp/radarr-manager:latest
RADARR_MANAGER_ENV_FILE=/mnt/user/appdata/radarr-manager/.env
RADARR_MANAGER_DEEP_ANALYSIS=true
```

## Project Structure

```
starr-butler/
├── src/
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── handlers.py      # Telegram message handlers
│   │   └── commands.py      # Bot commands (/start, /help, /stats)
│   ├── services/
│   │   ├── speech.py        # Whisper speech-to-text
│   │   ├── parser.py        # LLM media parser & router
│   │   ├── radarr.py        # Radarr client (movies)
│   │   ├── sonarr.py        # Sonarr client (TV shows)
│   │   ├── lidarr.py        # Lidarr client (music)
│   │   └── readarr.py       # Readarr client (books)
│   ├── models/
│   │   ├── media.py         # Pydantic models (Movie, TVShow, etc.)
│   │   └── config.py        # Configuration models
│   └── config/
│       └── settings.py      # Configuration loading
├── tests/
│   ├── test_speech.py
│   ├── test_parser.py
│   ├── test_radarr.py
│   ├── test_sonarr.py
│   └── test_integration.py
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── main.py                  # Entry point
```

## Implementation Plan

### Step 1: Setup & Basic Bot
1. Create new Python project `starr-butler` with pyproject.toml
2. Set up Telegram bot with BotFather
3. Implement basic message handlers (echo bot)
4. Add environment configuration for all *arr services

### Step 2: Speech-to-Text
1. Integrate OpenAI Whisper API
2. Handle voice message downloads from Telegram
3. Convert audio to text
4. Return transcription to user for confirmation

### Step 3: Media Parser & Router
1. Implement LLM-based media type detection (movie, tv_show, music, book)
2. Extract title, year/season, and metadata from natural language
3. Route to appropriate *arr service based on media type
4. Handle ambiguous requests (multiple matches, unclear titles)

### Step 4: Radarr Integration (Movies)
1. Implement Radarr API client
2. TMDB search for movie metadata
3. Add movies to Radarr with quality profiles
4. Return status to user
5. Optional: integrate radarr-manager for deep analysis

### Step 5: Sonarr Integration (TV Shows)
1. Implement Sonarr API client
2. TVDB/TMDB search for TV show metadata
3. Add series to Sonarr with season monitoring
4. Handle season-specific requests
5. Return status to user

### Step 6: Error Handling & Polish
1. Handle API failures gracefully
2. Add user-friendly error messages
3. Implement retry logic
4. Add logging and monitoring
5. Duplicate detection across services

### Step 7: Deployment
1. Create Docker image for starr-butler
2. Set up docker-compose with all *arr services
3. Deploy to home server (Unraid/NAS)
4. Configure systemd or cron for auto-restart

### Step 8 (Future): Lidarr & Readarr
1. Add music support (Lidarr)
2. Add book support (Readarr)
3. Expand parser to handle artist/album/author detection

## Security Considerations

### Authentication & Authorization
- Whitelist specific Telegram user IDs
- Only authorized users can add media
- Admin-only commands for configuration
- Per-user rate limits

### API Key Management
- Store all keys in environment variables
- Never commit .env files to version control
- Use read-only permissions where possible
- Separate API keys per *arr service

### Rate Limiting
- Limit requests per user per hour (prevent spam)
- OpenAI API cost controls
- *arr API rate limiting

## Example User Interactions

### Movie Request
```
User: [Voice message] "Add Dune Part 3 to my library"

Bot: 🎬 Processing your request...
     🎤 Transcription: "Add Dune Part 3 to my library"
     🔍 Detected: Movie
     🎬 Found: Dune: Part Three (2026)
     ⏳ Adding to Radarr...
     ✅ Success! "Dune: Part Three" added to your movie library.
```

### TV Show Request
```
User: [Voice] "Add Stranger Things season 6"

Bot: 📺 Processing your request...
     🎤 Transcription: "Add Stranger Things season 6"
     🔍 Detected: TV Show
     📺 Found: Stranger Things (2016)
     ⏳ Adding to Sonarr (monitoring Season 6)...
     ✅ Success! "Stranger Things" S06 added and monitoring.
```

### Music Request (Future)
```
User: [Voice] "Add the new Kendrick Lamar album"

Bot: 🎵 Processing your request...
     🎤 Transcription: "Add the new Kendrick Lamar album"
     🔍 Detected: Music
     🎵 Found: GNX by Kendrick Lamar (2024)
     ⏳ Adding to Lidarr...
     ✅ Success! "GNX" by Kendrick Lamar added to music library.
```

### Batch Request (Mixed Media)
```
User: [Voice] "Add The Batman 2, Stranger Things season 6, and the new Taylor Swift album"

Bot: 📋 Processing 3 requests...

     🎬 The Batman: Part II (2026)
     ✅ Added to Radarr

     📺 Stranger Things S06
     ✅ Added to Sonarr

     🎵 The Tortured Poets Department - Taylor Swift
     ✅ Added to Lidarr

     All done! 🎉
```

### Ambiguous Request with Confirmation
```
User: /add The Office

Bot: 🔍 Found multiple matches for "The Office":

     1️⃣ The Office (US) - 2005-2013 - TV Series
     2️⃣ The Office (UK) - 2001-2003 - TV Series

     Reply with number to confirm, or /cancel

User: 1

Bot: ✅ Adding "The Office (US)" to Sonarr...
     Success! All 9 seasons will be monitored.
```

## Success Metrics

- **Response Time**: < 5 seconds from voice to confirmation
- **Accuracy**: > 95% correct media type and title identification
- **Uptime**: 99%+ availability
- **Cost**: < $10/month for OpenAI API usage (casual household use)
- **Coverage**: Support for 2+ *arr services in Phase 1 (Radarr + Sonarr)

## Future Enhancements

- **Advanced Media Management**:
  - Browse library ("What action movies do I have?")
  - Recommendations ("Find me something like Inception")
  - Watch status tracking with Plex/Jellyfin
  - Delete/remove media via voice

- **Intelligent Features**:
  - Genre/mood-based requests ("Add a good thriller")
  - Cast/crew searches ("Movies with Ryan Gosling")
  - Franchise tracking ("Add all Marvel movies")
  - Automatic quality upgrades

- **Multi-Platform**:
  - Discord bot support
  - Slack integration
  - Web UI dashboard
  - Mobile app

- **Analytics**:
  - Usage statistics
  - Cost tracking (OpenAI API)
  - Library growth metrics
  - Popular requests

## Integration with Existing Projects

### radarr-manager
- **Current**: CLI tool for movie discovery and sync
- **Integration**: starr-butler can optionally use radarr-manager for:
  - Deep analysis mode for movie quality filtering
  - Automated discovery features
  - Quality scoring before adding

### Standalone Operation
starr-butler can also operate independently:
- Direct *arr API calls for all media types
- TMDB/TVDB/MusicBrainz searches
- No dependency on external manager tools
- Simpler deployment for TV/music/books

## Getting Started

### Prerequisites
- Telegram account and bot token (via [@BotFather](https://t.me/botfather))
- OpenAI API key
- Running *arr services (Radarr, Sonarr, etc.)
- Python 3.12+

### Quick Start
```bash
# Create new project
mkdir starr-butler
cd starr-butler

# Setup environment
python -m venv .venv
source .venv/bin/activate

# Install (after creating pyproject.toml)
pip install -e .[dev]

# Configure
cp .env.example .env
# Edit .env with your tokens and *arr service URLs

# Run locally
python main.py

# Or run with Docker
docker-compose up -d
```

### Docker Deployment (Unraid Example)
```yaml
version: '3.8'

services:
  starr-butler:
    image: mlamp/starr-butler:latest
    container_name: starr-butler
    restart: unless-stopped
    network_mode: host
    env_file:
      - /mnt/user/appdata/starr-butler/.env
    volumes:
      - /mnt/user/appdata/starr-butler/config:/config
      - /mnt/user/appdata/starr-butler/logs:/logs
```

## Naming Rationale

**"Starr Butler"** combines:
- **Starr**: Play on "*arr" (star/asterisk) - represents the entire *arr ecosystem
- **Butler**: Personal assistant that manages all your media needs

This name:
- ✅ Covers all *arr services (Radarr, Sonarr, Lidarr, Readarr)
- ✅ Suggests helpful, personal service
- ✅ Memorable and friendly
- ✅ Future-proof for expansion
- ✅ Not locked to single platform or media type

## License

MIT License (or match radarr-manager license)

---

## Development Roadmap

### Phase 1: Foundation (4-6 weeks)
- [ ] Project setup and configuration
- [ ] Telegram bot basic functionality
- [ ] Speech-to-text integration
- [ ] Media type detection
- [ ] Radarr integration (movies)
- [ ] Sonarr integration (TV shows)

### Phase 2: Enhancement (4-6 weeks)
- [ ] Batch request handling
- [ ] Search result confirmations
- [ ] User preference management
- [ ] Lidarr integration (music)
- [ ] Error handling improvements

### Phase 3: Advanced (Ongoing)
- [ ] radarr-manager deep analysis integration
- [ ] Readarr integration (books)
- [ ] Multi-user support
- [ ] Statistics and analytics
- [ ] Plex/Jellyfin integration

---

## Notes

- Designed for personal/home use at household scale
- Cost-effective for casual usage (Whisper: ~$0.006/minute)
- Can handle multiple users but optimized for family/friends
- Complements radarr-manager's discovery with voice-driven manual additions
- Natural extension of the *arr ecosystem philosophy
