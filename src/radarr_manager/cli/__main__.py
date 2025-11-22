from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

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
        help="Override the configured discovery provider (e.g. openai, gemini).",
    ),
    debug: bool = typer.Option(False, help="Enable debug logging to see detailed discovery process."),
) -> None:
    """Discover blockbuster releases using the configured content providers."""
    if debug:
        _setup_logging(logging.INFO)

    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    provider_instance = _safe_build_provider(load_result.settings, provider, debug=debug)
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
        help="Enable deep per-movie analysis with multi-source ratings validation and red flag detection.",
    ),
    debug: bool = typer.Option(False, help="Enable debug logging to see detailed discovery process."),
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

    provider_instance = _safe_build_provider(settings, None, debug=debug)
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
    year: int | None = typer.Option(None, help="Release year (used with --title for better accuracy)."),
    tmdb_id: int | None = typer.Option(None, help="TMDB ID (e.g., 123456)."),
    imdb_id: str | None = typer.Option(None, help="IMDB ID (e.g., tt1234567)."),
    dry_run: bool = typer.Option(True, help="Preview actions without modifying Radarr."),
    force: bool = typer.Option(False, help="Add movie even if a potential duplicate is detected."),
    debug: bool = typer.Option(False, help="Enable debug logging."),
) -> None:
    """Manually add a movie to Radarr by title, TMDB ID, or IMDB ID."""
    if debug:
        _setup_logging(logging.INFO)

    # Validate input: must provide either (title) or (tmdb_id) or (imdb_id)
    if not any([title, tmdb_id, imdb_id]):
        typer.secho(
            "Error: Must provide either --title, --tmdb-id, or --imdb-id",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    settings = load_result.settings
    try:
        settings.require_radarr()
    except SettingsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    asyncio.run(
        _run_add(
            settings=settings,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            dry_run=dry_run,
            force=force,
        ),
    )


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


def main() -> None:
    """Expose Typer app for the console script."""
    app()


def _safe_load_settings(load_even_if_missing: bool = False) -> Optional[SettingsLoadResult]:
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
            f"{idx}. {suggestion.title} ({year})"
            f" • confidence={suggestion.confidence:.2f}"
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

    # Apply deep analysis if requested
    filtered_suggestions = suggestions
    if deep_analysis:
        from radarr_manager.services import DeepAnalysisService

        typer.secho(
            f"\n[DEEP ANALYSIS] Analyzing {len(suggestions)} movies...",
            fg=typer.colors.CYAN,
            bold=True,
        )
        analyzer = DeepAnalysisService(debug=debug)
        analyses = []
        for movie in suggestions:
            analysis = await analyzer.analyze_movie(movie)
            analyses.append(analysis)

        # Display analysis results
        typer.echo()
        for i, analysis in enumerate(analyses, 1):
            meta = analysis.rating_details
            typer.secho(f"{i}. {analysis.movie.title}", bold=True)
            typer.echo(f"   Quality Score: {analysis.quality_score:.1f}/10")

            # Format ratings with proper None handling
            imdb_rating = meta['imdb_rating'] if meta['imdb_rating'] is not None else 'N/A'
            imdb_votes = f"{meta['imdb_votes']:,}" if meta['imdb_votes'] else '0'
            rt_critics = f"{meta['rt_critics_score']}%" if meta['rt_critics_score'] is not None else 'N/A'
            rt_audience = f"{meta['rt_audience_score']}%" if meta['rt_audience_score'] is not None else 'N/A'
            metacritic = meta['metacritic_score'] if meta['metacritic_score'] is not None else 'N/A'

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
        skipped_count = len(suggestions) - len(filtered_suggestions)

        typer.secho(
            f"Deep Analysis Complete: {len(filtered_suggestions)} approved, "
            f"{skipped_count} rejected\n",
            fg=typer.colors.CYAN,
            bold=True,
        )

        if not filtered_suggestions:
            typer.secho(
                "No movies passed deep analysis quality gates.",
                fg=typer.colors.YELLOW,
            )
            return

    assert settings_state.radarr_base_url is not None
    assert settings_state.radarr_api_key is not None

    async with RadarrClient(
        base_url=settings_state.radarr_base_url,
        api_key=settings_state.radarr_api_key,
    ) as client:
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
        f"Queued: {len(summary.queued)} | Skipped: {len(summary.skipped)} | Errors: {len(summary.errors)}",
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
) -> None:
    """Add a single movie to Radarr by lookup."""
    assert settings.radarr_base_url is not None
    assert settings.radarr_api_key is not None

    # Build search term based on provided parameters
    if tmdb_id:
        search_term = f"tmdb:{tmdb_id}"
        typer.echo(f"Searching for movie with TMDB ID: {tmdb_id}")
    elif imdb_id:
        search_term = f"imdb:{imdb_id}"
        typer.echo(f"Searching for movie with IMDB ID: {imdb_id}")
    elif title:
        if year:
            search_term = f"{title} {year}"
            typer.echo(f"Searching for movie: {title} ({year})")
        else:
            search_term = title
            typer.echo(f"Searching for movie: {title}")
    else:
        typer.secho("Error: No search criteria provided", fg=typer.colors.RED)
        return

    async with RadarrClient(
        base_url=settings.radarr_base_url,
        api_key=settings.radarr_api_key,
    ) as client:
        # Lookup movie
        try:
            results = await client.lookup_movie(search_term)
        except Exception as exc:
            typer.secho(f"Error looking up movie: {exc}", fg=typer.colors.RED)
            return

        if not results:
            typer.secho("No movies found matching search criteria.", fg=typer.colors.YELLOW)
            return

        # Display results and let user pick if multiple matches
        if len(results) > 1:
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

        typer.secho(f"\nFound: {movie_title} ({movie_year})", fg=typer.colors.GREEN)

        # Display movie details
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
                "tmdb_id": movie_data.get("tmdbId"),
                "imdb_id": movie_data.get("imdbId"),
            },
        )

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

        # Display results
        if dry_run:
            typer.secho("\n[DRY RUN] No changes made to Radarr", fg=typer.colors.CYAN)

        if summary.queued:
            typer.secho(f"✓ Successfully queued: {movie_title}", fg=typer.colors.GREEN)
        elif summary.skipped:
            typer.secho(f"⊘ Skipped: {movie_title}", fg=typer.colors.YELLOW)
            if summary.skipped:
                typer.echo(f"   Reason: {summary.skipped[0]}")
        elif summary.errors:
            typer.secho(f"✗ Error adding: {movie_title}", fg=typer.colors.RED)
            if summary.errors:
                typer.echo(f"   Error: {summary.errors[0]}")


if __name__ == "__main__":
    main()
