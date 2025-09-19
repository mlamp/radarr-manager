import pytest

from radarr_manager.config import Settings
from radarr_manager.providers.factory import build_provider
from radarr_manager.providers.base import ProviderError
from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.providers.static import StaticListProvider


def test_factory_returns_static_by_default() -> None:
    settings = Settings()
    provider = build_provider(settings)
    assert isinstance(provider, StaticListProvider)


def test_factory_returns_openai_provider_when_requested() -> None:
    settings = Settings(llm_provider="openai", openai_api_key="fake-key", openai_model="gpt-test")
    provider = build_provider(settings)
    assert isinstance(provider, OpenAIProvider)


def test_openai_provider_requires_api_key() -> None:
    settings = Settings(llm_provider="openai")
    with pytest.raises(ProviderError):
        build_provider(settings)
