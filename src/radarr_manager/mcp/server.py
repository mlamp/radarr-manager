"""MCP server implementation with radarr-manager tools."""

import asyncio
from typing import Any

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.routing import Route

from radarr_manager.clients.radarr import RadarrClient
from radarr_manager.config.settings import Settings
from radarr_manager.mcp.schemas import (
    AddMovieParams,
    AddMovieResponse,
    AnalyzeQualityParams,
    DiscoverMoviesParams,
    DiscoverMoviesResponse,
    MovieSuggestion,
    QualityAnalysisResponse,
    SearchMovieParams,
    SearchMovieResponse,
    SyncMoviesParams,
    SyncMoviesResponse,
    SyncResult,
)
from radarr_manager.models.movie import MovieSuggestion as MovieSuggestionModel
from radarr_manager.providers.factory import build_provider
from radarr_manager.services.analysis import DeepAnalysisService
from radarr_manager.services.discovery import DiscoveryService
from radarr_manager.services.sync import SyncService


def create_mcp_server() -> Server:
    """Create and configure the MCP server with all tools."""
    server = Server("radarr-manager")

    # Load settings once at startup
    settings = Settings()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return [
            Tool(
                name="search_movie",
                description=(
                    "Check if a movie already exists in Radarr. "
                    "Returns whether the movie is in the library."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Movie title"},
                        "year": {
                            "type": "integer",
                            "description": "Release year (optional)",
                        },
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="add_movie",
                description=(
                    "Add a movie to Radarr with intelligent quality gating. "
                    "Blocks low-quality movies unless force=true. "
                    "Returns detailed quality analysis and status."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Movie title"},
                        "year": {"type": "integer", "description": "Release year"},
                        "tmdb_id": {"type": "integer", "description": "TMDB ID"},
                        "imdb_id": {"type": "string", "description": "IMDB ID"},
                        "force": {
                            "type": "boolean",
                            "description": "Bypass quality gate",
                            "default": False,
                        },
                        "deep_analysis": {
                            "type": "boolean",
                            "description": "Enable quality analysis",
                            "default": True,
                        },
                        "quality_threshold": {
                            "type": "number",
                            "description": "Minimum quality score (0-10)",
                            "default": 5.0,
                            "minimum": 0.0,
                            "maximum": 10.0,
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Preview without modifying",
                            "default": True,
                        },
                    },
                },
            ),
            Tool(
                name="analyze_quality",
                description=(
                    "Get quality analysis for a movie without adding it. "
                    "Returns multi-source ratings, scores, and recommendations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Movie title"},
                        "year": {"type": "integer", "description": "Release year"},
                        "tmdb_id": {"type": "integer", "description": "TMDB ID"},
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="discover_movies",
                description=(
                    "Discover trending blockbuster movies using AI. "
                    "Returns list of movie suggestions with reasons."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of movies",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                        "region": {
                            "type": "string",
                            "description": "Region code (e.g., 'US')",
                        },
                    },
                },
            ),
            Tool(
                name="sync_movies",
                description=(
                    "Discover and sync movies to Radarr in one operation. "
                    "Includes quality filtering and duplicate detection."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of movies",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Preview without modifying",
                            "default": True,
                        },
                        "deep_analysis": {
                            "type": "boolean",
                            "description": "Enable quality analysis",
                            "default": True,
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        if name == "search_movie":
            return await _search_movie(settings, arguments)
        elif name == "add_movie":
            return await _add_movie(settings, arguments)
        elif name == "analyze_quality":
            return await _analyze_quality(settings, arguments)
        elif name == "discover_movies":
            return await _discover_movies(settings, arguments)
        elif name == "sync_movies":
            return await _sync_movies(settings, arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    return server


async def _search_movie(settings: Settings, arguments: dict[str, Any]) -> list[TextContent]:
    """Search if movie exists in Radarr."""
    params = SearchMovieParams(**arguments)

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key.get_secret_value(),
    ) as client:
        # Search by title
        results = await client.lookup_movie(params.title, params.year)

        if not results:
            response = SearchMovieResponse(exists=False, message=f"Movie not found: {params.title}")
            return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        # Check if movie is in Radarr
        movie = results[0]
        tmdb_id = movie.get("tmdbId")

        if tmdb_id:
            existing = await client.get_movie_by_tmdb(tmdb_id)
            if existing:
                response = SearchMovieResponse(
                    exists=True,
                    movie=existing,
                    message=f"✓ {params.title} is already in Radarr",
                )
                return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        response = SearchMovieResponse(
            exists=False,
            movie=movie,
            message=f"Movie found but not in Radarr: {params.title}",
        )
        return [TextContent(type="text", text=response.model_dump_json(indent=2))]


async def _add_movie(settings: Settings, arguments: dict[str, Any]) -> list[TextContent]:
    """Add movie to Radarr with quality gating."""
    params = AddMovieParams(**arguments)

    # Need at least one identifier
    if not any([params.title, params.tmdb_id, params.imdb_id]):
        response = AddMovieResponse(
            success=False,
            error="missing_identifier",
            message="Must provide title, TMDB ID, or IMDB ID",
        )
        return [TextContent(type="text", text=response.model_dump_json(indent=2))]

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key.get_secret_value(),
    ) as client:
        # Lookup movie
        if params.tmdb_id:
            results = await client.lookup_movie_by_tmdb(params.tmdb_id)
        elif params.imdb_id:
            results = await client.lookup_movie_by_imdb(params.imdb_id)
        else:
            results = await client.lookup_movie(params.title, params.year)

        if not results:
            response = AddMovieResponse(
                success=False,
                error="not_found",
                message=f"Movie not found: {params.title or params.tmdb_id or params.imdb_id}",
            )
            return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        movie_data = results[0]
        movie_title = movie_data.get("title", "Unknown")
        movie_year = movie_data.get("year")
        movie_tmdb_id = movie_data.get("tmdbId")

        # Check if already exists
        if movie_tmdb_id:
            existing = await client.get_movie_by_tmdb(movie_tmdb_id)
            if existing:
                response = AddMovieResponse(
                    success=False,
                    error="already_exists",
                    message=f"Movie already in Radarr: {movie_title} ({movie_year})",
                    movie={
                        "title": movie_title,
                        "year": movie_year,
                        "tmdb_id": movie_tmdb_id,
                    },
                )
                return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        # Deep analysis if enabled
        analysis = None
        quality_score = None

        if params.deep_analysis:
            analysis_service = DeepAnalysisService(
                openai_api_key=settings.openai_api_key.get_secret_value(),
                openai_model=settings.openai_model,
            )

            movie_suggestion = MovieSuggestionModel(
                title=movie_title,
                year=movie_year,
                tmdb_id=movie_tmdb_id,
                imdb_id=movie_data.get("imdbId"),
            )

            analysis = await analysis_service.analyze_movie(movie_suggestion)
            quality_score = analysis.quality_score

            # Quality gate check
            if not params.force and quality_score < params.quality_threshold:
                quality_analysis = QualityAnalysisResponse(
                    overall_score=quality_score,
                    threshold=params.quality_threshold,
                    passed=False,
                    recommendation=analysis.recommendation,
                    ratings=analysis.rating_details,
                    red_flags=analysis.red_flags,
                )

                response = AddMovieResponse(
                    success=False,
                    error="quality_too_low",
                    message=(
                        f"Movie has poor ratings "
                        f"(score: {quality_score:.1f}/10, threshold: {params.quality_threshold})"
                    ),
                    movie={
                        "title": movie_title,
                        "year": movie_year,
                        "tmdb_id": movie_tmdb_id,
                    },
                    quality_analysis=quality_analysis,
                    can_override=True,
                    override_instructions=("To add anyway, call add_movie again with force=true"),
                )
                return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        # Add to Radarr (unless dry run)
        if not params.dry_run:
            added = await client.add_movie(
                movie_data=movie_data,
                quality_profile_id=settings.radarr_quality_profile_id,
                root_folder_path=settings.radarr_root_folder_path,
                minimum_availability=settings.radarr_minimum_availability,
                monitored=settings.radarr_monitor,
                tags=[settings.radarr_tags] if settings.radarr_tags else [],
            )

            if not added:
                response = AddMovieResponse(
                    success=False,
                    error="add_failed",
                    message=f"Failed to add movie to Radarr: {movie_title}",
                )
                return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        # Success response
        warning = None
        if params.force and analysis and quality_score and quality_score < params.quality_threshold:
            warning = "This movie has poor ratings but was added due to force=true"

        quality_analysis = None
        if analysis:
            quality_analysis = QualityAnalysisResponse(
                overall_score=quality_score,
                threshold=params.quality_threshold,
                passed=quality_score >= params.quality_threshold,
                recommendation=analysis.recommendation,
                ratings=analysis.rating_details,
                red_flags=analysis.red_flags,
            )

        action = "Would add" if params.dry_run else "Added"
        response = AddMovieResponse(
            success=True,
            message=f"{action}: {movie_title} ({movie_year})",
            movie={"title": movie_title, "year": movie_year, "tmdb_id": movie_tmdb_id},
            quality_analysis=quality_analysis,
            warning=warning,
        )
        return [TextContent(type="text", text=response.model_dump_json(indent=2))]


async def _analyze_quality(settings: Settings, arguments: dict[str, Any]) -> list[TextContent]:
    """Analyze movie quality without adding."""
    params = AnalyzeQualityParams(**arguments)

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key.get_secret_value(),
    ) as client:
        # Lookup movie
        if params.tmdb_id:
            results = await client.lookup_movie_by_tmdb(params.tmdb_id)
        else:
            results = await client.lookup_movie(params.title, params.year)

        if not results:
            return [
                TextContent(
                    type="text",
                    text=f'{{"error": "Movie not found: {params.title}"}}',
                )
            ]

        movie_data = results[0]
        movie_title = movie_data.get("title", "Unknown")
        movie_year = movie_data.get("year")
        movie_tmdb_id = movie_data.get("tmdbId")

        # Run analysis
        analysis_service = DeepAnalysisService(
            openai_api_key=settings.openai_api_key.get_secret_value(),
            openai_model=settings.openai_model,
        )

        movie_suggestion = MovieSuggestionModel(
            title=movie_title,
            year=movie_year,
            tmdb_id=movie_tmdb_id,
            imdb_id=movie_data.get("imdbId"),
        )

        analysis = await analysis_service.analyze_movie(movie_suggestion)

        quality_analysis = QualityAnalysisResponse(
            overall_score=analysis.quality_score,
            threshold=None,
            passed=analysis.should_add,
            recommendation=analysis.recommendation,
            ratings=analysis.rating_details,
            red_flags=analysis.red_flags,
        )

        return [TextContent(type="text", text=quality_analysis.model_dump_json(indent=2))]


async def _discover_movies(settings: Settings, arguments: dict[str, Any]) -> list[TextContent]:
    """Discover blockbuster movies."""
    params = DiscoverMoviesParams(**arguments)

    # Build provider
    provider = build_provider(
        provider_name=settings.llm_provider,
        openai_api_key=(
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        ),
        openai_model=settings.openai_model,
    )

    # Run discovery
    discovery_service = DiscoveryService(provider=provider)
    suggestions = await discovery_service.discover(
        limit=params.limit, region=params.region or settings.radarr_region
    )

    # Convert to response schema
    movies = [
        MovieSuggestion(
            title=movie.title,
            year=movie.year,
            tmdb_id=movie.tmdb_id,
            imdb_id=movie.imdb_id,
            reason=movie.reason,
        )
        for movie in suggestions
    ]

    response = DiscoverMoviesResponse(
        success=True,
        movies=movies,
        count=len(movies),
        message=f"Discovered {len(movies)} blockbuster movies",
    )

    return [TextContent(type="text", text=response.model_dump_json(indent=2))]


async def _sync_movies(settings: Settings, arguments: dict[str, Any]) -> list[TextContent]:
    """Discover and sync movies to Radarr."""
    params = SyncMoviesParams(**arguments)

    # Build provider
    provider = build_provider(
        provider_name=settings.llm_provider,
        openai_api_key=(
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        ),
        openai_model=settings.openai_model,
    )

    # Create services
    discovery_service = DiscoveryService(provider=provider)

    analysis_service = None
    if params.deep_analysis:
        analysis_service = DeepAnalysisService(
            openai_api_key=settings.openai_api_key.get_secret_value(),
            openai_model=settings.openai_model,
        )

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key.get_secret_value(),
    ) as radarr_client:
        sync_service = SyncService(
            radarr_client=radarr_client,
            discovery_service=discovery_service,
            analysis_service=analysis_service,
        )

        # Run sync
        summary = await sync_service.sync(
            limit=params.limit,
            dry_run=params.dry_run,
            quality_profile_id=settings.radarr_quality_profile_id,
            root_folder_path=settings.radarr_root_folder_path,
            minimum_availability=settings.radarr_minimum_availability,
            monitored=settings.radarr_monitor,
            tags=[settings.radarr_tags] if settings.radarr_tags else [],
        )

        # Build results
        results = []
        for movie in summary.added:
            results.append(
                SyncResult(
                    title=movie.title,
                    year=movie.year,
                    status="added",
                    reason="Successfully added to Radarr",
                    quality_score=getattr(movie, "quality_score", None),
                )
            )

        for movie in summary.existing:
            results.append(
                SyncResult(
                    title=movie.title,
                    year=movie.year,
                    status="exists",
                    reason="Already in Radarr",
                )
            )

        for movie in summary.skipped:
            results.append(
                SyncResult(
                    title=movie.title,
                    year=movie.year,
                    status="skipped",
                    reason="Skipped due to quality threshold",
                    quality_score=getattr(movie, "quality_score", None),
                )
            )

        summary_counts = {
            "added": len(summary.added),
            "existing": len(summary.existing),
            "skipped": len(summary.skipped),
            "queued": summary.queued,
        }

        action = "Would sync" if params.dry_run else "Synced"
        response = SyncMoviesResponse(
            success=True,
            results=results,
            summary=summary_counts,
            message=(
                f"{action} {summary.queued} movies "
                f"(added: {len(summary.added)}, exists: {len(summary.existing)}, "
                f"skipped: {len(summary.skipped)})"
            ),
        )

        return [TextContent(type="text", text=response.model_dump_json(indent=2))]


async def run_mcp_server(settings: Settings) -> None:
    """Run the MCP server with stdio transport."""
    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_mcp_http_server(settings: Settings, host: str, port: int) -> None:
    """Run the MCP server with HTTP/SSE transport."""
    from starlette.responses import Response

    server = create_mcp_server()
    sse = SseServerTransport("/mcp/messages")

    async def handle_sse(request):
        """Handle SSE connections."""
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    async def handle_messages(request):
        """Handle POST messages."""
        await sse.handle_post_message(request.scope, request.receive, request._send)

    starlette_app = Starlette(
        routes=[
            Route("/mcp/sse", endpoint=handle_sse),
            Route("/mcp/messages", endpoint=handle_messages, methods=["POST"]),
        ]
    )

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def main() -> None:
    """Entry point for MCP server."""
    from radarr_manager.config.settings import load_settings

    settings = load_settings().settings
    asyncio.run(run_mcp_server(settings))


if __name__ == "__main__":
    main()
