"""Built-in discovery prompts."""

from __future__ import annotations

from pathlib import Path

from radarr_manager.discovery.prompt import DiscoveryPrompt

PROMPTS_DIR = Path(__file__).parent


def get_builtin_prompt(name: str) -> DiscoveryPrompt:
    """Load a built-in discovery prompt by name."""
    prompt_file = PROMPTS_DIR / f"{name}.yaml"
    if not prompt_file.exists():
        available = list_builtin_prompts()
        raise ValueError(f"Unknown prompt '{name}'. Available: {', '.join(available)}")
    return DiscoveryPrompt.from_yaml(prompt_file)


def list_builtin_prompts() -> list[str]:
    """List available built-in prompts."""
    return [p.stem for p in PROMPTS_DIR.glob("*.yaml")]


# Preload default prompt for quick access
def get_default_prompt() -> DiscoveryPrompt:
    """Get the default discovery prompt."""
    return get_builtin_prompt("default")


__all__ = ["get_builtin_prompt", "get_default_prompt", "list_builtin_prompts"]
