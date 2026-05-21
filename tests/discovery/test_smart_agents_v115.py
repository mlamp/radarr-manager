"""Tests for v1.15 agent behavior with LibraryIndex injection."""

from __future__ import annotations

import httpx
import pytest
import respx

from radarr_manager.clients.radarr import LibraryIndex
from radarr_manager.discovery.smart.agents.fetch import SmartFetchAgent
from radarr_manager.discovery.smart.agents.validator import SmartValidatorAgent


def _library_with(*entries: tuple[str, int]) -> LibraryIndex:
    return LibraryIndex.from_movies(
        [
            {"title": title, "year": year, "tmdbId": idx + 1, "added": "2025-01-01T00:00:00Z"}
            for idx, (title, year) in enumerate(entries)
        ]
    )


class TestFetchAgentPreFilter:
    """Fetch agent pre-filters parsed movies against LibraryIndex before returning."""

    @pytest.mark.asyncio
    async def test_owned_titles_dropped_and_counted(self, monkeypatch):
        agent = SmartFetchAgent(
            api_url="http://stub",
            debug=False,
            library_index=_library_with(("Owned", 2025), ("AlsoOwned", 2024)),
        )

        async def fake_fetch(url):
            return "stub-html"

        def fake_get_parser(name):
            class FakeParser:
                def parse(self, content, url):
                    from radarr_manager.discovery.parsers import ParsedMovie

                    return [
                        ParsedMovie(title="Owned", year=2025, source="imdb", extra={}),
                        ParsedMovie(title="Fresh", year=2026, source="imdb", extra={}),
                        ParsedMovie(title="AlsoOwned", year=2024, source="imdb", extra={}),
                    ]

            return FakeParser()

        monkeypatch.setattr(agent, "_fetch_content", fake_fetch)
        monkeypatch.setattr(
            "radarr_manager.discovery.smart.agents.fetch.get_parser",
            fake_get_parser,
        )

        report = await agent.execute(url="http://example.com", parser="imdb_moviemeter")
        titles = [m.title for m in report.movies]
        assert titles == ["Fresh"]
        assert report.stats["pre_filtered_in_library"] == 2
        # Report should surface a Pre-filter section so the orchestrator sees why
        # the candidate count shrank.
        assert any(s.heading == "Pre-filter" for s in report.sections)

    @pytest.mark.asyncio
    async def test_no_index_means_no_pre_filter(self, monkeypatch):
        agent = SmartFetchAgent(api_url="http://stub", library_index=None)

        async def fake_fetch(url):
            return "stub-html"

        def fake_get_parser(name):
            class FakeParser:
                def parse(self, content, url):
                    from radarr_manager.discovery.parsers import ParsedMovie

                    return [ParsedMovie(title="X", year=2025, source="imdb", extra={})]

            return FakeParser()

        monkeypatch.setattr(agent, "_fetch_content", fake_fetch)
        monkeypatch.setattr(
            "radarr_manager.discovery.smart.agents.fetch.get_parser",
            fake_get_parser,
        )

        report = await agent.execute(url="http://example.com", parser="imdb_moviemeter")
        assert report.stats["pre_filtered_in_library"] == 0
        assert [m.title for m in report.movies] == ["X"]


class TestValidatorShortCircuit:
    """Validator skips per-title Radarr lookups for titles the index already owns."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_owned_title_does_not_hit_radarr(self):
        agent = SmartValidatorAgent(
            radarr_base_url="http://radarr:7878",
            radarr_api_key="x",
            debug=False,
            library_index=_library_with(("Owned", 2025)),
        )

        # Stub Radarr lookup. We then assert ONLY "Fresh" hit the network —
        # "Owned" must be short-circuited by the LibraryIndex.
        lookup_route = respx.get("http://radarr:7878/api/v3/movie/lookup").mock(
            return_value=httpx.Response(200, json=[])
        )

        report = await agent.execute(
            movies=[
                {"title": "Owned", "year": 2025},
                {"title": "Brand New Title", "year": 2026},
            ],
            enrich=True,
            filter_in_library=True,
        )

        called_terms = [call.request.url.params["term"] for call in lookup_route.calls]
        assert "Owned" not in called_terms
        assert "Brand New Title" in called_terms
        assert report.stats["in_library_filtered"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_index_falls_back_to_per_title_lookup(self):
        agent = SmartValidatorAgent(
            radarr_base_url="http://radarr:7878",
            radarr_api_key="x",
            debug=False,
            library_index=None,
        )
        lookup_route = respx.get("http://radarr:7878/api/v3/movie/lookup").mock(
            return_value=httpx.Response(200, json=[])
        )
        await agent.execute(
            movies=[{"title": "Brand New Title", "year": 2025}],
            enrich=True,
            filter_in_library=True,
        )
        # With no index, validator must consult Radarr for every title.
        assert lookup_route.call_count == 1
