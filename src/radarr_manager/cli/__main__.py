from __future__ import annotations

import asyncio
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
) -> None:
    """Discover blockbuster releases using the configured content providers."""
    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    provider_instance = _safe_build_provider(load_result.settings, provider)
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
) -> None:
    """Synchronize discovered movies with Radarr."""
    load_result = _safe_load_settings()
    if load_result is None:
        raise typer.Exit(code=1)

    settings = load_result.settings
    try:
        settings.require_radarr()
    except SettingsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    provider_instance = _safe_build_provider(settings, None)
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


def _safe_build_provider(settings: Settings, override: str | None):
    try:
        return build_provider(settings, override=override)
    except Exception as exc:  # pragma: no cover - surfaced through CLI error handling
        typer.secho(str(exc), fg=typer.colors.RED)
        return None


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


async def _run_sync(
    *,
    discovery: DiscoveryService,
    settings_state: Settings,
    limit: int,
    dry_run: bool,
    force: bool,
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
        service = SyncService(
            client,
            quality_profile_id=settings_state.quality_profile_id,
            root_folder_path=settings_state.root_folder_path,
            monitor=settings_state.monitor,
            minimum_availability=settings_state.minimum_availability,
            tags=settings_state.tags,
        )
        summary = await service.sync(suggestions, dry_run=dry_run, force=force)

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


if __name__ == "__main__":
    main()
