"""Optional OpenAI-compatible LLM HTTP client factory."""

import httpx

from bid_system.platform.config import ProviderSettings


def create_llm_client(
    provider: ProviderSettings, timeout_seconds: float
) -> httpx.AsyncClient | None:
    """Construct an optional LLM client without opening a network connection."""
    if not provider.enabled or provider.base_url is None or provider.api_key is None:
        return None
    return httpx.AsyncClient(
        base_url=provider.base_url,
        headers={"Authorization": f"Bearer {provider.api_key.get_secret_value()}"},
        timeout=httpx.Timeout(timeout_seconds),
    )
