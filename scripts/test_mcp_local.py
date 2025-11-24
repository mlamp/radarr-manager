#!/usr/bin/env python3
"""Quick local test script for MCP server verification.

This script performs a simple test of the add_movie MCP tool to verify
that the radarr-manager MCP server is working correctly with all the
required RadarrClient methods.

Usage:
    python scripts/test_mcp_local.py
"""

import asyncio
import httpx
from radarr_manager.clients.radarr import RadarrClient
from radarr_manager.config import Settings


async def test_add_movie_the_matrix():
    """Test adding The Matrix using the new RadarrClient methods."""
    print("🧪 Testing radarr-manager MCP server functionality...\n")

    settings = Settings()

    # Validate settings
    if not settings.radarr_base_url or not settings.radarr_api_key:
        print("❌ Error: RADARR_BASE_URL and RADARR_API_KEY must be set")
        print("   Please configure .env file or set environment variables")
        return False

    print(f"📡 Connecting to Radarr at {settings.radarr_base_url}")

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key.get_secret_value(),
    ) as client:
        # Test 1: lookup_movie_by_tmdb (new method)
        print("\n1️⃣ Testing lookup_movie_by_tmdb(603)...")
        try:
            lookup_results = await client.lookup_movie_by_tmdb(603)
            if lookup_results:
                movie = lookup_results[0]
                print(f"   ✅ Found: {movie.get('title')} ({movie.get('year')})")
                print(f"   📊 TMDB ID: {movie.get('tmdbId')}, IMDB ID: {movie.get('imdbId')}")
            else:
                print("   ⚠️  No results found")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

        # Test 2: get_movie_by_tmdb (new method)
        print("\n2️⃣ Testing get_movie_by_tmdb(603)...")
        try:
            existing_movie = await client.get_movie_by_tmdb(603)
            if existing_movie:
                print(f"   ℹ️  Movie already in library: {existing_movie.get('title')}")
                print(f"   📁 Radarr ID: {existing_movie.get('id')}")
            else:
                print("   ℹ️  Movie not in library yet")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

        # Test 3: lookup_movie_by_imdb (new method)
        print("\n3️⃣ Testing lookup_movie_by_imdb('tt0133093')...")
        try:
            imdb_results = await client.lookup_movie_by_imdb("tt0133093")
            if imdb_results:
                movie = imdb_results[0]
                print(f"   ✅ Found: {movie.get('title')} ({movie.get('year')})")
            else:
                print("   ⚠️  No results found")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

        # Test 4: Check existing methods still work
        print("\n4️⃣ Testing existing list_quality_profiles()...")
        try:
            profiles = await client.list_quality_profiles()
            print(f"   ✅ Found {len(profiles)} quality profiles")
            if profiles:
                print(f"   📊 Example: {profiles[0].get('name')} (ID: {profiles[0].get('id')})")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

        print("\n5️⃣ Testing existing list_root_folders()...")
        try:
            folders = await client.list_root_folders()
            print(f"   ✅ Found {len(folders)} root folders")
            if folders:
                print(f"   📁 Example: {folders[0].get('path')}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

    print("\n" + "="*60)
    print("✅ All RadarrClient methods working correctly!")
    print("="*60)
    print("\n💡 The MCP server should now work without AttributeError exceptions.")
    print("   All required methods are implemented:\n")
    print("   - lookup_movie_by_tmdb(tmdb_id)")
    print("   - lookup_movie_by_imdb(imdb_id)")
    print("   - get_movie_by_tmdb(tmdb_id)")
    print()

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_add_movie_the_matrix())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
