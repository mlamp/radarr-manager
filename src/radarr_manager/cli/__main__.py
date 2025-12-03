from __future__ import annotations

import asyncio
import logging
from typing import Any

import typer

from radarr_manager import __version__
from radarr_manager.clients.radarr import RadarrClient
from radarr_manager.config import Settings, SettingsError, SettingsLoadResult, load_settings
from radarr_manager.models import MovieSuggestion
from radarr_manager.providers.factory import build_provider
from radarr_manager.services.discovery import DiscoveryService
from radarr_manager.services.sync import SyncService

app = typer.Typer(
    add_completion=False,
    help="Discover, curate, and synchronize blockbuster movie lists with Radarr.",
)


@app.callback()
def _cli_entry(ctx: typer.Context) -> None:
    """Entrypoint for the radarr-manager CLI."""
    ctx.obj = {} if ctx.obj is None else ctx.obj


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def discover(
    limit: int = typer.Option(5, help="Maximum number of movies to return."),
    provider: str | None = typer.Option(
        None,
        help="[Deprecated] Use --discovery-mode instead.",
    ),
    discovery_mode: str | None = typer.Option(
        None,
        help="Discovery mode: openai, hybrid, scraper, or static.",
    ),
    debug: bool = typer.Option(
        False, help="Enable debug logging to see detailed discovery process."
    ),
) -> None:
    """Discover blockbuster releases using the configured content providers."""
    if debug:
        _setup_logging(logging.INFO)

    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    # Prefer discovery_mode, fall back to deprecated provider arg
    mode_override = discovery_mode or provider
    provider_instance = _safe_build_provider(load_result.settings, mode_override, debug=debug)
    if provider_instance is None:
        raise typer.Exit(code=1)

    discovery = DiscoveryService(provider_instance, region=load_result.settings.region)

    suggestions = asyncio.run(discovery.discover(limit=limit))
    _render_discover_results(suggestions, provider_name=provider_instance.name)


@app.command()
def sync(
    limit: int = typer.Option(5, help="Number of suggestions to evaluate during sync."),
    dry_run: bool = typer.Option(True, help="Preview actions without modifying Radarr."),
    force: bool = typer.Option(
        False,
        help="Add movies even if a potential duplicate is detected.",
    ),
    deep_analysis: bool = typer.Option(
        False,
        help=(
            "Enable deep per-movie analysis with multi-source ratings "
            "validation and red flag detection."
        ),
    ),
    discovery_mode: str | None = typer.Option(
        None,
        help="Discovery mode: openai, hybrid, scraper, or static.",
    ),
    debug: bool = typer.Option(
        False, help="Enable debug logging to see detailed discovery process."
    ),
) -> None:
    """Synchronize discovered movies with Radarr."""
    if debug:
        _setup_logging(logging.INFO)

    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    settings = load_result.settings
    try:
        settings.require_radarr()
    except SettingsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    provider_instance = _safe_build_provider(settings, discovery_mode, debug=debug)
    if provider_instance is None:
        raise typer.Exit(code=1)

    discovery = DiscoveryService(provider_instance, region=settings.region)

    asyncio.run(
        _run_sync(
            discovery=discovery,
            settings_state=settings,
            limit=limit,
            dry_run=dry_run,
            force=force,
            deep_analysis=deep_analysis,
            debug=debug,
        ),
    )


@app.command()
def add(
    title: str | None = typer.Option(None, help="Movie title to search for."),
    year: int | None = typer.Option(
        None, help="Release year (used with --title for better accuracy)."
    ),
    tmdb_id: int | None = typer.Option(None, help="TMDB ID (e.g., 123456)."),
    imdb_id: str | None = typer.Option(None, help="IMDB ID (e.g., tt1234567)."),
    dry_run: bool = typer.Option(True, help="Preview actions without modifying Radarr."),
    force: bool = typer.Option(False, help="Bypass quality gate and add regardless of score."),
    deep_analysis: bool = typer.Option(
        True,
        help="Enable quality analysis with multi-source ratings (default: enabled).",
    ),
    quality_threshold: float = typer.Option(
        5.0,
        help="Minimum quality score (0-10) required to auto-add movie.",
        min=0.0,
        max=10.0,
    ),
    json_output: bool = typer.Option(
        True, "--json/--no-json", help="Output as JSON for programmatic use."
    ),
    debug: bool = typer.Option(False, help="Enable debug logging."),
) -> None:
    """Manually add a movie to Radarr with intelligent quality gating."""
    if debug:
        _setup_logging(logging.INFO)

    # Validate input: must provide either (title) or (tmdb_id) or (imdb_id)
    if not any([title, tmdb_id, imdb_id]):
        if json_output:
            _output_json_error(
                "invalid_input", "Must provide either --title, --tmdb-id, or --imdb-id"
            )
        else:
            typer.secho(
                "Error: Must provide either --title, --tmdb-id, or --imdb-id",
                fg=typer.colors.RED,
            )
        raise typer.Exit(code=1)

    load_result = _safe_load_settings()
    if load_result is None:
        if json_output:
            _output_json_error("config_error", "Failed to load settings")
        raise typer.Exit(code=5)

    settings = load_result.settings
    try:
        settings.require_radarr()
    except SettingsError as exc:
        if json_output:
            _output_json_error("config_error", str(exc))
        else:
            typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=5) from exc

    exit_code = asyncio.run(
        _run_add(
            settings=settings,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            dry_run=dry_run,
            force=force,
            deep_analysis=deep_analysis,
            quality_threshold=quality_threshold,
            json_output=json_output,
            debug=debug,
        ),
    )
    raise typer.Exit(code=exit_code)


@app.command()
def config(show_sources: bool = typer.Option(False, help="Display provider hints.")) -> None:
    """Describe configuration expectations."""
    load_result = _safe_load_settings(load_even_if_missing=True)
    if load_result is None:
        raise typer.Exit(code=1)

    settings = load_result.settings
    values: dict[str, Any] = {
        "radarr_base_url": settings.radarr_base_url or "<unset>",
        "radarr_api_key": "<set>" if settings.radarr_api_key else "<unset>",
        "llm_provider": settings.llm_provider or "<unset>",
        "openai_model": settings.openai_model or "<unset>",
        "quality_profile_id": settings.quality_profile_id or "<unset>",
        "root_folder_path": settings.root_folder_path or "<unset>",
        "minimum_availability": settings.minimum_availability or "<unset>",
        "monitor": settings.monitor,
        "tags": settings.tags or [],
        "cache_ttl_hours": settings.cache_ttl_hours,
        "region": settings.region or "<unset>",
    }

    for key, value in values.items():
        typer.echo(f"{key}: {value}")

    if show_sources:
        source_hint = load_result.source_path or "<env/.env>"
        typer.echo(f"resolved_from: {source_hint}")
        typer.echo(
            "Provider keys: OPENAI_API_KEY, GEMINI_API_KEY, GROK_API_KEY."
            " Configure ~/.config/radarr-manager/config.toml for persistent settings.",
        )


@app.command()
def serve(
    host: str | None = typer.Option(
        None, help="Host to bind MCP server (default: MCP_HOST or 127.0.0.1)"
    ),
    port: int | None = typer.Option(
        None, help="Port to bind MCP server (default: MCP_PORT or 8091)"
    ),
    transport: str | None = typer.Option(
        None, help="Transport: stdio or sse (default: MCP_TRANSPORT or stdio)"
    ),
    debug: bool = typer.Option(False, help="Enable debug logging"),
) -> None:
    """Run radarr-manager as an MCP service for AI agents.

    Starts a long-running MCP (Model Context Protocol) server that exposes
    radarr-manager functionality as structured tools for AI agents like
    Telegram bots, Discord bots, or other LLM applications.

    Transport modes:
    - stdio: Process communication via stdin/stdout (for subprocess integration)
    - sse: HTTP/SSE server on network (for remote clients)
      Endpoints: /mcp/sse (SSE stream), /mcp/messages (POST)

    Tools available:
    - search_movie: Check if movie exists in Radarr
    - add_movie: Add with quality gating
    - analyze_quality: Get quality analysis
    - discover_movies: Find blockbusters
    - sync_movies: Discover and sync

    Example:
        radarr-manager serve --host 0.0.0.0 --port 8091 --transport sse
    """
    if debug:
        _setup_logging(logging.DEBUG)
        # Enable debug logging for MCP SDK to trace SSE communication
        logging.getLogger("mcp").setLevel(logging.DEBUG)
        logging.getLogger("radarr_manager.mcp").setLevel(logging.DEBUG)

    # Load settings for defaults
    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    settings = load_result.settings

    # CLI overrides or settings defaults
    final_host = host if host is not None else settings.mcp_host
    final_port = port if port is not None else settings.mcp_port
    final_transport = transport if transport is not None else settings.mcp_transport

    # Import MCP server functions
    from radarr_manager.mcp.server import run_mcp_http_server, run_mcp_server

    if final_transport == "sse":
        typer.secho(
            f"🚀 Starting MCP HTTP/SSE server on http://{final_host}:{final_port}...",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            "🚀 Starting MCP stdio server...",
            fg=typer.colors.GREEN,
        )

    typer.echo(
        "Available tools: search_movie, add_movie, analyze_quality, discover_movies, sync_movies"
    )
    typer.echo("Press Ctrl+C to stop")

    try:
        if final_transport == "sse":
            asyncio.run(run_mcp_http_server(settings, final_host, final_port))
        else:
            asyncio.run(run_mcp_server(settings))
    except KeyboardInterrupt:
        typer.echo("\n👋 MCP server stopped")


def main() -> None:
    """Expose Typer app for the console script."""
    app()


def _safe_load_settings(load_even_if_missing: bool = False) -> SettingsLoadResult | None:
    try:
        return load_settings()
    except SettingsError as exc:
        if load_even_if_missing:
            typer.secho(
                f"Warning: configuration incomplete – {exc}",
                fg=typer.colors.YELLOW,
            )
            return SettingsLoadResult(settings=Settings(), source_path=None)
        typer.secho(str(exc), fg=typer.colors.RED)
        return None


def _safe_build_provider(settings: Settings, override: str | None, debug: bool = False):
    try:
        return build_provider(settings, override=override, debug=debug)
    except Exception as exc:  # pragma: no cover - surfaced through CLI error handling
        typer.secho(str(exc), fg=typer.colors.RED)
        return None


def _setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for debug mode."""
    logging.basicConfig(
        format="%(message)s",
        level=level,
        force=True,
    )


def _render_discover_results(
    suggestions: list[MovieSuggestion],
    *,
    provider_name: str,
) -> None:
    if not suggestions:
        typer.secho("No suggestions discovered.", fg=typer.colors.YELLOW)
        return

    header = f"Provider: {provider_name}"
    typer.secho(header, fg=typer.colors.CYAN)
    if provider_name == "openai":
        typer.echo("Using OpenAI Responses + web_search for fresh box-office intel.")
    for idx, suggestion in enumerate(suggestions, start=1):
        year = suggestion.year or "TBA"
        typer.echo(
            f"{idx}. {suggestion.title} ({year})" f" • confidence={suggestion.confidence:.2f}"
        )
        if suggestion.overview:
            typer.echo(f"   {suggestion.overview}")
        if suggestion.sources:
            typer.echo(f"   sources: {', '.join(suggestion.sources)}")

        # Display TMDB/IMDB IDs if available in metadata
        if suggestion.metadata:
            ids = []
            if tmdb_id := suggestion.metadata.get("tmdb_id"):
                ids.append(f"tmdb:{tmdb_id}")
            if imdb_id := suggestion.metadata.get("imdb_id"):
                ids.append(f"imdb:{imdb_id}")
            if ids:
                typer.echo(f"   ids: {', '.join(ids)}")


async def _run_sync(
    *,
    discovery: DiscoveryService,
    settings_state: Settings,
    limit: int,
    dry_run: bool,
    force: bool,
    deep_analysis: bool = False,
    debug: bool = False,
) -> None:
    suggestions = await discovery.discover(limit=limit)

    if not suggestions:
        typer.secho("No suggestions to sync.", fg=typer.colors.YELLOW)
        return

    assert settings_state.radarr_base_url is not None
    assert settings_state.radarr_api_key is not None

    async with RadarrClient(
        base_url=settings_state.radarr_base_url,
        api_key=settings_state.radarr_api_key,
    ) as client:
        # Enrich suggestions with ratings data from Radarr
        from radarr_manager.services import EnrichmentService

        if debug:
            typer.secho(
                f"\n[ENRICHMENT] Fetching ratings for {len(suggestions)} movies from Radarr...",
                fg=typer.colors.CYAN,
            )
        enrichment = EnrichmentService(client, debug=debug)
        suggestions = await enrichment.enrich_suggestions(suggestions)

        # Filter out movies already in library (detected during enrichment)
        in_library = [s for s in suggestions if s.metadata and s.metadata.get("in_library")]
        not_in_library = [s for s in suggestions if not (s.metadata and s.metadata.get("in_library"))]

        if in_library and debug:
            typer.secho(
                f"\n[SKIP] {len(in_library)} movies already in library:",
                fg=typer.colors.YELLOW,
            )
            for movie in in_library:
                typer.echo(f"  - {movie.title}")

        # Apply deep analysis if requested (only for movies NOT in library)
        filtered_suggestions = not_in_library
        if deep_analysis and not_in_library:
            from radarr_manager.services import DeepAnalysisService

            typer.secho(
                f"\n[DEEP ANALYSIS] Analyzing {len(not_in_library)} new movies...",
                fg=typer.colors.CYAN,
                bold=True,
            )
            analyzer = DeepAnalysisService(debug=debug)
            analyses = []
            for movie in not_in_library:
                analysis = await analyzer.analyze_movie(movie)
                analyses.append(analysis)

            # Display analysis results
            typer.echo()
            for i, analysis in enumerate(analyses, 1):
                meta = analysis.rating_details
                typer.secho(f"{i}. {analysis.movie.title}", bold=True)
                typer.echo(f"   Quality Score: {analysis.quality_score:.1f}/10")

                # Format ratings with proper None handling
                imdb_rating = meta["imdb_rating"] if meta["imdb_rating"] is not None else "N/A"
                imdb_votes = f"{meta['imdb_votes']:,}" if meta["imdb_votes"] else "0"
                rt_critics = (
                    f"{meta['rt_critics_score']}%" if meta["rt_critics_score"] is not None else "N/A"
                )
                rt_audience = (
                    f"{meta['rt_audience_score']}%" if meta["rt_audience_score"] is not None else "N/A"
                )
                metacritic = meta["metacritic_score"] if meta["metacritic_score"] is not None else "N/A"

                typer.echo(
                    f"   Ratings: IMDb {imdb_rating} ({imdb_votes} votes) | "
                    f"RT Critics {rt_critics} | RT Audience {rt_audience} | Metacritic {metacritic}"
                )
                typer.echo(f"   {analysis.recommendation}")
                if analysis.red_flags:
                    typer.secho(f"   ⚠ Red Flags ({len(analysis.red_flags)}):", fg=typer.colors.RED)
                    for flag in analysis.red_flags[:3]:
                        typer.echo(f"     • {flag}")
                if analysis.strengths:
                    typer.secho(f"   ✓ Strengths ({len(analysis.strengths)}):", fg=typer.colors.GREEN)
                    for strength in analysis.strengths[:3]:
                        typer.echo(f"     • {strength}")
                if analysis.should_add:
                    typer.secho("   → WILL ADD", fg=typer.colors.GREEN, bold=True)
                else:
                    typer.secho("   → WILL SKIP", fg=typer.colors.YELLOW, bold=True)
                typer.echo()

            # Filter to only movies that passed deep analysis
            filtered_suggestions = [a.movie for a in analyses if a.should_add]
            rejected_count = len(not_in_library) - len(filtered_suggestions)

            typer.secho(
                f"Deep Analysis Complete: {len(filtered_suggestions)} approved, "
                f"{rejected_count} rejected, {len(in_library)} already in library\n",
                fg=typer.colors.CYAN,
                bold=True,
            )

            if not filtered_suggestions:
                typer.secho(
                    "No movies passed deep analysis quality gates.",
                    fg=typer.colors.YELLOW,
                )
                return

        # Sync approved movies to Radarr
        service = SyncService(
            client,
            quality_profile_id=settings_state.quality_profile_id,
            root_folder_path=settings_state.root_folder_path,
            monitor=settings_state.monitor,
            minimum_availability=settings_state.minimum_availability,
            tags=settings_state.tags,
        )
        summary = await service.sync(filtered_suggestions, dry_run=dry_run, force=force)

    typer.secho(
        f"Queued: {len(summary.queued)} | "
        f"Skipped: {len(summary.skipped)} | "
        f"Errors: {len(summary.errors)}",
        fg=typer.colors.CYAN,
    )
    if summary.queued:
        typer.echo("Queued titles:")
        for title in summary.queued:
            typer.echo(f"  - {title}")
    if summary.skipped:
        typer.echo("Skipped titles:")
        for title in summary.skipped:
            typer.echo(f"  - {title}")
    if summary.errors:
        typer.secho("Errors:", fg=typer.colors.RED)
        for reason in summary.errors:
            typer.echo(f"  - {reason}")


async def _run_add(
    *,
    settings: Settings,
    title: str | None,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str | None,
    dry_run: bool,
    force: bool,
    deep_analysis: bool = True,
    quality_threshold: float = 5.0,
    json_output: bool = True,
    debug: bool = False,
) -> int:
    """
    Add a single movie to Radarr with intelligent quality gating.

    Returns exit code:
    - 0: Success
    - 1: Movie not found
    - 2: Already exists (duplicate)
    - 3: Quality too low (rejected by quality gate)
    - 4: Radarr API error
    - 5: Other errors
    """
    import json

    assert settings.radarr_base_url is not None
    assert settings.radarr_api_key is not None

    # Build search term based on provided parameters
    if tmdb_id:
        search_term = f"tmdb:{tmdb_id}"
        if not json_output:
            typer.echo(f"Searching for movie with TMDB ID: {tmdb_id}")
    elif imdb_id:
        search_term = f"imdb:{imdb_id}"
        if not json_output:
            typer.echo(f"Searching for movie with IMDB ID: {imdb_id}")
    elif title:
        if year:
            search_term = f"{title} {year}"
            if not json_output:
                typer.echo(f"Searching for movie: {title} ({year})")
        else:
            search_term = title
            if not json_output:
                typer.echo(f"Searching for movie: {title}")
    else:
        _output_json_error("invalid_input", "No search criteria provided") if json_output else None
        return 5

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key,
    ) as client:
        # Lookup movie
        try:
            results = await client.lookup_movie(search_term)
        except Exception as exc:
            if json_output:
                _output_json_error("radarr_error", f"Error looking up movie: {exc}")
            else:
                typer.secho(f"Error looking up movie: {exc}", fg=typer.colors.RED)
            return 4

        if not results:
            if json_output:
                _output_json_error("movie_not_found", "No movies found matching search criteria")
            else:
                typer.secho("No movies found matching search criteria.", fg=typer.colors.YELLOW)
            return 1

        # Display results and let user pick if multiple matches
        if len(results) > 1 and not json_output:
            typer.echo(f"\nFound {len(results)} matches:")
            for idx, result in enumerate(results, start=1):
                movie_title = result.get("title", "Unknown")
                movie_year = result.get("year", "Unknown")
                typer.echo(f"  {idx}. {movie_title} ({movie_year})")
            typer.echo("\nUsing first match. Use --tmdb-id or --imdb-id for exact matching.")

        # Use first result
        movie_data = results[0]
        movie_title = movie_data.get("title", "Unknown")
        movie_year = movie_data.get("year", "Unknown")
        movie_tmdb_id = movie_data.get("tmdbId")
        movie_imdb_id = movie_data.get("imdbId")

        if not json_output:
            typer.secho(f"\nFound: {movie_title} ({movie_year})", fg=typer.colors.GREEN)
            if overview := movie_data.get("overview"):
                typer.echo(f"Overview: {overview[:200]}{'...' if len(overview) > 200 else ''}")

        # Convert lookup result to MovieSuggestion for sync
        suggestion = MovieSuggestion(
            title=movie_title,
            year=movie_year if isinstance(movie_year, int) else None,
            overview=movie_data.get("overview", ""),
            franchise=movie_data.get("studio", ""),
            confidence=1.0,  # Manual addition = full confidence
            sources=["manual"],
            metadata={
                "tmdb_id": movie_tmdb_id,
                "imdb_id": movie_imdb_id,
            },
        )

        # Deep analysis with quality gating
        analysis = None
        quality_score = None
        if deep_analysis:
            from radarr_manager.services import DeepAnalysisService

            if not json_output:
                typer.secho(
                    f"\n[QUALITY ANALYSIS] Analyzing {movie_title}...", fg=typer.colors.CYAN
                )

            analyzer = DeepAnalysisService(debug=debug)
            analysis = await analyzer.analyze_movie(suggestion)
            quality_score = analysis.quality_score

            if not json_output:
                typer.echo(
                    f"Quality Score: {quality_score:.1f}/10 (threshold: {quality_threshold})"
                )
                typer.echo(f"Recommendation: {analysis.recommendation}")
                if analysis.red_flags:
                    typer.secho(f"Red Flags ({len(analysis.red_flags)}):", fg=typer.colors.RED)
                    for flag in analysis.red_flags[:3]:
                        typer.echo(f"  • {flag}")

            # Quality gate check (bypass with --force)
            if not force and quality_score < quality_threshold:
                if json_output:
                    _output_json_with_quality_analysis(
                        success=False,
                        error="quality_too_low",
                        message=(
                            f"Movie has poor ratings "
                            f"(score: {quality_score:.1f}/10, threshold: {quality_threshold})"
                        ),
                        movie_info={
                            "title": movie_title,
                            "year": movie_year,
                            "tmdb_id": movie_tmdb_id,
                        },
                        analysis=analysis,
                        quality_threshold=quality_threshold,
                        can_override=True,
                        override_cmd=(
                            f'radarr-manager add --title "{movie_title}" '
                            f"--year {movie_year} --force"
                        ),
                    )
                else:
                    typer.secho(
                        f"\n✗ Quality gate blocked: {movie_title} "
                        f"(score: {quality_score:.1f}/10 < {quality_threshold})",
                        fg=typer.colors.RED,
                    )
                    typer.echo("   Use --force to override and add anyway")
                return 3

        # Use SyncService to add the movie
        service = SyncService(
            client,
            quality_profile_id=settings.quality_profile_id,
            root_folder_path=settings.root_folder_path,
            monitor=settings.monitor,
            minimum_availability=settings.minimum_availability,
            tags=settings.tags,
        )

        summary = await service.sync([suggestion], dry_run=dry_run, force=force)

        # Determine exit code and output
        if summary.queued:
            if json_output:
                warning_msg = None
                if force and analysis and quality_score and quality_score < quality_threshold:
                    warning_msg = "This movie has poor ratings but was added due to --force flag"

                _output_json_with_quality_analysis(
                    success=True,
                    message=f"Successfully added: {movie_title} ({movie_year})",
                    movie_info={
                        "title": movie_title,
                        "year": movie_year,
                        "tmdb_id": movie_tmdb_id,
                        "imdb_id": movie_imdb_id,
                    },
                    analysis=analysis,
                    quality_threshold=quality_threshold if analysis else None,
                    warning=warning_msg,
                )
            else:
                if dry_run:
                    typer.secho("\n[DRY RUN] No changes made to Radarr", fg=typer.colors.CYAN)
                if force and analysis and quality_score and quality_score < quality_threshold:
                    typer.secho(
                        f"⚠ Successfully queued: {movie_title} (quality override used)",
                        fg=typer.colors.YELLOW,
                    )
                else:
                    typer.secho(f"✓ Successfully queued: {movie_title}", fg=typer.colors.GREEN)
            return 0

        elif summary.skipped:
            if json_output:
                output = {
                    "success": False,
                    "error": "already_exists",
                    "message": f"Movie already in Radarr library: {movie_title} ({movie_year})",
                    "movie": {"title": movie_title, "year": movie_year, "tmdb_id": movie_tmdb_id},
                    "override_instructions": "This check cannot be bypassed with --force",
                }
                typer.echo(json.dumps(output, indent=2))
            else:
                if dry_run:
                    typer.secho("\n[DRY RUN] No changes made to Radarr", fg=typer.colors.CYAN)
                typer.secho(f"⊘ Skipped: {movie_title}", fg=typer.colors.YELLOW)
                typer.echo(
                    f"   Reason: {summary.skipped[0] if summary.skipped else 'Already exists'}"
                )
            return 2

        elif summary.errors:
            if json_output:
                _output_json_error(
                    "radarr_error",
                    f"Error adding movie: {movie_title}",
                    details={"error": summary.errors[0] if summary.errors else "unknown"},
                )
            else:
                typer.secho(f"✗ Error adding: {movie_title}", fg=typer.colors.RED)
                if summary.errors:
                    typer.echo(f"   Error: {summary.errors[0]}")
            return 4

        # Fallback
        return 5


def _output_json_error(
    error_code: str, message: str, details: dict[str, Any] | None = None
) -> None:
    """Output a JSON error message."""
    import json

    output = {
        "success": False,
        "error": error_code,
        "message": message,
    }
    if details:
        output["details"] = details
    typer.echo(json.dumps(output, indent=2))


def _output_json_with_quality_analysis(
    success: bool,
    message: str,
    movie_info: dict[str, Any],
    analysis: Any = None,
    quality_threshold: float | None = None,
    error: str | None = None,
    can_override: bool = False,
    override_cmd: str | None = None,
    warning: str | None = None,
) -> None:
    """Output JSON with detailed quality analysis."""
    import json

    output: dict[str, Any] = {
        "success": success,
        "message": message,
        "movie": movie_info,
    }

    if error:
        output["error"] = error

    if warning:
        output["warning"] = warning

    # Add detailed quality analysis if available
    if analysis:
        ratings_meta = analysis.rating_details
        quality_analysis = {
            "overall_score": analysis.quality_score,
            "threshold": quality_threshold,
            "passed": analysis.should_add,
            "recommendation": analysis.recommendation,
            "ratings": {
                "rotten_tomatoes": {
                    "critics_score": ratings_meta.get("rt_critics_score"),
                    "audience_score": ratings_meta.get("rt_audience_score"),
                },
                "imdb": {
                    "score": ratings_meta.get("imdb_rating"),
                    "votes": ratings_meta.get("imdb_votes"),
                },
                "metacritic": {
                    "score": ratings_meta.get("metacritic_score"),
                },
            },
            "red_flags": analysis.red_flags,
        }
        output["quality_analysis"] = quality_analysis

    if can_override:
        output["can_override"] = True
    if override_cmd:
        output["override_instructions"] = f"To add this movie anyway, use: {override_cmd}"

    typer.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
