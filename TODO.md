# radarr-manager TODO

## Current Status (v1.4.0-dev)

### ✅ Recently Completed
- **NEW: `radarr-manager add` command** - Manually add movies by title/year, TMDB ID, or IMDB ID
- Extended movie discovery time window from 2 to 4 months, then to 3 months backward + 4 months forward (7 months total)
- Added support for pre-release movies without IMDb ratings
- Expanded studio coverage to include prestige studios (Lionsgate, A24, Sony Pictures, Neon, Searchlight Pictures, Focus Features)
- Added Aura Entertainment, IFC Films, Bleecker Street to studio list
- Added explicit mid-budget theatrical releases clause in SYSTEM_PROMPT
- Enhanced user prompt to search multiple sources (box office, IMDb, TMDB, RT) and include action-comedies/dramedies
- Added Rotten Tomatoes in-theaters URL hint for currently-playing well-reviewed films
- Added `--debug` flag to `discover` and `sync` commands for detailed logging
- Built and pushed multi-arch Docker images (linux/amd64 + linux/arm64)
- Fixed dry-run duplicate detection bug
- Switched from LLM-provided IDs to title/year-based movie lookup

### 🎯 User Goals

**Primary Goal**: Improve movie discovery to include high-quality mid-budget theatrical releases that are currently being excluded.

**Specific Movies User Wants Discovered**:
1. **The Housemaid (2025)** ✅ NOW APPEARING (as of v1.3.0, position #16/16 with limit=20)
   - Release: December 19, 2025
   - Stars: Sydney Sweeney
   - Studio: Lionsgate
   - Genre: Psychological thriller
   - Status: **SUCCESS** - Extended time window + prestige studio inclusion fixed this

2. **Code 3 (2025)** ❌ STILL NOT APPEARING (After Extensive Prompt Engineering)
   - Release: September 12, 2025
   - Stars: Rainn Wilson, Lil Rel Howery
   - IMDb: 7.2/10 (passes 6.5 threshold)
   - RT: 70% fresh
   - Genre: Action-comedy (paramedic drama)
   - Distributor: Aura Entertainment
   - Status: **PROBLEM** - Not appearing with gpt-4o-mini (16-19 results) or gpt-4o (6 results)
   - Root Cause: LLM's web_search tool doesn't find Code 3 in mainstream box office prediction articles
   - Conclusion: Prompt engineering alone cannot solve this - need manual addition feature

## 🔍 Analysis: Why "Code 3" Isn't Appearing

### Technical Criteria (All Met ✅)
- ✅ Release date: Sept 12, 2025 (within 4-month window)
- ✅ IMDb rating: 7.2/10 (above 6.5 threshold)
- ✅ Rotten Tomatoes: 70% fresh
- ✅ Wide theatrical release confirmed
- ✅ Recognizable cast (The Office's Rainn Wilson)
- ✅ Festival pedigree (TIFF 2024 premiere)

### Why It's Being Excluded (Hypothesis)
1. **Studio/Distributor Issue**: Aura Entertainment is not in the "major studio" list
   - Current prompt mentions: Marvel, DC, Disney, Universal, Warner Bros, Lionsgate, A24, Sony Pictures, Neon, Searchlight Pictures, Focus Features
   - Aura Entertainment is a smaller distributor not on this list

2. **Genre Bias**: "Paramedic action-comedy" doesn't fit typical blockbuster or prestige categories
   - LLM prioritizes: franchises, tentpoles, award contenders, superhero films
   - Mid-budget comedies get deprioritized

3. **Competition**: LLM returning only 16/20 requested suggestions
   - Major franchises crowd it out: Avatar, Wicked, Knives Out, Super Mario
   - Prestige picks win: The Housemaid, Die My Love, Bugonia
   - Code 3 falls below the cutoff line

4. **Web Search Results**: LLM's web_search tool may not find enough "authoritative sources" ranking it highly
   - Big franchises dominate box office prediction articles
   - Mid-budget releases get less pre-release coverage

### Current Discovery Results (limit=20)
With gpt-4o-mini, the system returns ~16 movies:
- Major franchises: Avatar 3, Wicked 2, Knives Out 3, Super Mario 2, Now You See Me 3
- Superhero/Action: Captain America, Black Phone 2
- Prestige/A24-style: The Housemaid, Die My Love, Bugonia, A Big Bold Beautiful Journey
- Family: Freakier Friday, Lilo & Stitch
- Holiday: Jingle Bell Heist

**Code 3 doesn't fit any of these buckets cleanly.**

## 🛠️ Proposed Solutions

### Option 1: Expand Studio/Distributor List (Easiest)
Add more theatrical distributors to the SYSTEM_PROMPT:
```
Include: [...existing...], Aura Entertainment, Neon, GKIDS, IFC Films, Roadside Attractions,
Bleecker Street, Magnolia Pictures, and other established theatrical distributors.
```

**Pros**: Simple one-line change
**Cons**: Might not be enough - genre bias still exists

### Option 2: Add Mid-Budget Category (Recommended)
Modify prompt to explicitly include "strong mid-budget theatrical releases":
```
In addition to blockbusters and prestige films, include well-reviewed mid-budget theatrical releases
(IMDb 7.0+, RT 60%+) with recognizable casts from established theatrical distributors.
```

**Pros**: Directly addresses the gap
**Cons**: Makes prompt longer, may dilute focus

### Option 3: Lower Confidence Threshold
Accept movies with confidence >= 0.60 instead of filtering too aggressively:
```python
# In provider or discovery service
if suggestion.confidence >= 0.60:  # Was implicitly 0.70+
    include_movie(suggestion)
```

**Pros**: More inclusive
**Cons**: May include lower-quality suggestions

### Option 4: Increase Request Limit
Ask LLM for more movies (30-40) to see if Code 3 appears further down:
```bash
radarr-manager discover --limit 40 --debug
```

**Pros**: Zero code changes
**Cons**: Higher API costs, may still not appear

### Option 5: Manual Movie Addition Feature (Long-term)
Add new CLI command to bypass LLM discovery:
```bash
radarr-manager add --title "Code 3" --year 2025 --tmdb-id 123456
```

**Pros**: Guaranteed inclusion, useful for edge cases
**Cons**: Requires new feature development

### Option 6: Multi-Pass Discovery (Advanced)
Run discovery twice with different prompts and merge results:
- Pass 1: Current prompt (blockbusters + prestige)
- Pass 2: "Mid-budget theatrical releases with 7.0+ IMDb"

**Pros**: Best coverage, no compromises
**Cons**: 2x API costs, more complex

## 📋 Recommended Next Steps

### ✅ Completed (v1.4.0-dev)
1. ✅ **Test with higher limit**: Tested limit=20, 25, 30 - Code 3 doesn't appear
2. ✅ **Add Aura Entertainment**: Added to studio list in SYSTEM_PROMPT along with IFC Films, Bleecker Street
3. ✅ **Add mid-budget clause**: Added explicit, detailed mid-budget theatrical releases clause
4. ✅ **Test with gpt-4o**: gpt-4o returns only 6 movies (worse coverage than gpt-4o-mini's 16-19)
5. ✅ **Extend time window**: Changed from "past month" to "past three months" (Sept-Nov 2025)
6. ✅ **Enhanced user prompt**: Added guidance to search multiple sources (box office, IMDb, TMDB, RT)

### ⚠️ Findings
- **Prompt engineering limitations**: Despite extensive modifications, Code 3 doesn't appear in LLM web search results
- **Web search bias**: LLM's web_search tool prioritizes major franchises and well-marketed films
- **Coverage gap**: Mid-budget releases from smaller distributors lack coverage in mainstream box office prediction sites

### ✅ Short-term (COMPLETED)
1. ✅ **Implemented `radarr-manager add` command**: Manual movie additions bypassing LLM discovery
   - Syntax: `radarr-manager add --title "Code 3" --year 2025`
   - Or: `radarr-manager add --tmdb-id 123456`
   - Or: `radarr-manager add --imdb-id tt1234567`
   - Includes `--dry-run`, `--force`, `--debug` flags
   - Uses existing SyncService for duplicate detection and adding
   - Solves the Code 3 problem and future edge cases

### Long-term (Future)
6. **Configurable prompts**: Allow users to customize discovery criteria via config
7. **Multi-source discovery**: Add TMDB trending API as fallback/supplement
8. **Genre preferences**: Let users specify preferred genres (action, comedy, thriller, etc.)

## 🧪 Testing Commands

```bash
# Test current discovery
source .venv/bin/activate
radarr-manager discover --limit 20 --debug

# Search for specific movie
radarr-manager discover --limit 20 --debug 2>&1 | grep -i "code"

# Test with higher limit
radarr-manager discover --limit 40 --debug

# Test with gpt-4o (more selective but higher quality)
export OPENAI_MODEL=gpt-4o
radarr-manager discover --limit 20 --debug

# Test dry-run sync
radarr-manager sync --dry-run --limit 10 --debug

# NEW: Manually add movies
radarr-manager add --title "Code 3" --year 2025 --dry-run
radarr-manager add --tmdb-id 123456 --dry-run
radarr-manager add --imdb-id tt1234567 --dry-run

# Add movie for real (without dry-run)
radarr-manager add --title "Code 3" --year 2025 --no-dry-run

# Force add even if duplicate detected
radarr-manager add --title "Code 3" --year 2025 --no-dry-run --force
```

## 📝 Notes

### Model Behavior Differences
- **gpt-4o-mini**: Returns ~16-17 movies when asking for 20, broader selection, cost-efficient
- **gpt-4o**: Returns only 3-4 movies when asking for 20, very conservative, expensive

### .env Configuration Issue
- Direct .env edits don't always reload (config caching issue?)
- Workaround: Use explicit env vars: `export OPENAI_MODEL=gpt-4o`
- TODO: Investigate why config loader prefers some source over .env

### Docker Base Image
- Current: `python:3.12-slim` (3.12.12) - stable, well-tested
- Available: `python:3.13-slim` (3.13.9) - newer, ~5-10% faster
- Recommendation: **Keep 3.12** for production stability

## 🔗 Relevant Files

- `src/radarr_manager/cli/__main__.py:104-147` - **NEW:** `add` command implementation
- `src/radarr_manager/cli/__main__.py:304-410` - **NEW:** `_run_add` function
- `src/radarr_manager/providers/openai.py:15-34` - SYSTEM_PROMPT (discovery criteria)
- `src/radarr_manager/providers/openai.py:132-140` - User prompt with RT in-theaters URL hint
- `src/radarr_manager/cli/__main__.py:42,70` - CLI with --debug flag
- `src/radarr_manager/services/sync.py:56-77` - Title/year-based lookup logic
- `src/radarr_manager/clients/radarr.py:40-44` - RadarrClient.lookup_movie()
- `pyproject.toml:3` - Version (currently 1.3.0, next: 1.4.0)
- `.env:5` - OPENAI_MODEL configuration

## 📊 Success Metrics

- ✅ The Housemaid now appearing in discovery results
- ❌ Code 3 still not appearing despite extensive prompt improvements (requires manual addition feature)
- ✅ Debug mode provides visibility into LLM decisions
- ✅ Extended time window now covers 7 months (past 3 months + next 4 months)
- ✅ Dry-run mode now correctly detects duplicates
- ✅ SYSTEM_PROMPT now explicitly includes mid-budget releases, action-comedies, dramedies
- ✅ User prompt now instructs LLM to search multiple sources (box office, IMDb, TMDB, RT)
- ⚠️ gpt-4o-mini returns 16-19 movies (better coverage), gpt-4o returns only 6 (too conservative)
- ✅ **Improved mid-budget discovery**: Now finding films like Christy, Weapons, Caught Stealing, Freakier Friday
- ❌ Code 3 still not found despite RT in-theaters URL hint and Aug-Nov timeframe specification

## 📝 Prompt Changes Made (v1.4.0-dev)

### SYSTEM_PROMPT Changes:
1. Time window: "past month" → "past three months" (line 21)
2. Added studios: Aura Entertainment, IFC Films, Bleecker Street (line 24)
3. Added mid-budget clause: "IMPORTANT: Also include well-reviewed mid-budget theatrical releases with IMDb 7.0+ or RT 60%+ ratings, recognizable casts (TV/film actors), and wide theatrical distribution - this includes action-comedies, dramedies, and genre films from distributors like Aura Entertainment, even if they are not franchise films or Oscar contenders. Prioritize quality ratings over marketing budget." (lines 25-27)

### User Prompt Changes (_build_prompt):
1. Changed "strong commercial traction or franchise momentum" → "blockbusters, franchises, prestige films, AND mid-budget releases"
2. Added explicit search sources: "box office predictions, IMDb/TMDB, Rotten Tomatoes (https://www.rottentomatoes.com/browse/movies_in_theaters for currently playing), and recent 2025 theatrical releases from Aug-Nov"
3. Added genre examples: "action-comedies, dramedies"
4. Made more concise to avoid JSON truncation with higher limits

---

**Last Updated**: 2025-11-14
**Version**: 1.4.0-dev
**Status**: ✅ All priority features implemented. Ready for release after testing.
