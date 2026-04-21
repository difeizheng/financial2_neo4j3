"""LLM provider factory."""
from config import LLM_PROVIDER
from .base import LLMProvider, SheetStructure, SectionInfo


def get_provider(provider: str | None = None) -> LLMProvider:
    """Return the configured LLM provider instance."""
    name = (provider or LLM_PROVIDER).lower()
    if name == "siliconflow":
        from .siliconflow_provider import SiliconFlowProvider
        return SiliconFlowProvider()
    if name == "anthropic" or name == "claude":
        from .claude_provider import ClaudeProvider
        return ClaudeProvider()
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Choose: siliconflow | anthropic | openai | ollama")
