"""OpenAI-compatible client factory.

Primary provider: Meterless Nightshift (its OpenAI-compatible runtime, default http://127.0.0.1:8088/v1),
which routes to NVIDIA Nemotron lanes (e.g. METERLESS_MODEL=meterless/deep). NVIDIA NIM is an optional
fallback that is only used when LLM_PROVIDER=nim is set explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from openai import OpenAI

from src.config import MissingSetting, Settings

PROVIDERS = ("meterless", "nim")


@dataclass
class LLMTarget:
    client: OpenAI
    model: str
    provider: str
    chat_extra_headers: dict[str, str] = field(default_factory=dict)


def select_provider(s: Settings) -> str:
    """meterless unless LLM_PROVIDER=nim is set explicitly."""
    provider = (s.llm_provider or "meterless").strip().lower()
    if provider not in PROVIDERS:
        raise MissingSetting(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)} (got '{s.llm_provider}')")
    return provider


def build_llm(s: Settings) -> LLMTarget:
    provider = select_provider(s)
    if provider == "nim":
        s.require("nvidia_nim_api_key", "nemotron_model")
        client = OpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=120)
        return LLMTarget(client, s.nemotron_model, "nim")
    if not s.meterless_api_key:
        raise MissingSetting("Set METERLESS_API_KEY (the Meterless Nightshift runtime token) in .env, "
                             "or set LLM_PROVIDER=nim with NVIDIA_NIM_API_KEY + NEMOTRON_MODEL to use the NIM fallback")
    client = OpenAI(base_url=s.meterless_base_url, api_key=s.meterless_api_key, timeout=180,
                    default_headers={"meterless-app": s.meterless_app_id})
    return LLMTarget(client, s.meterless_model, "meterless", {"meterless-scope": "user"})
