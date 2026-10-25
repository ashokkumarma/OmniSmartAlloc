"""OpenAI-compatible client factory for NVIDIA Nemotron via NVIDIA NIM or Meterless Runtime."""
from __future__ import annotations

from dataclasses import dataclass, field

from openai import OpenAI

from src.config import MissingSetting, Settings


@dataclass
class LLMTarget:
    client: OpenAI
    model: str
    provider: str
    chat_extra_headers: dict[str, str] = field(default_factory=dict)


def build_llm(s: Settings) -> LLMTarget:
    provider = s.llm_provider.lower() or ("nim" if s.nvidia_nim_api_key else "meterless" if s.meterless_api_key else "")
    if provider == "nim":
        s.require("nvidia_nim_api_key", "nemotron_model")
        client = OpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=120)
        return LLMTarget(client, s.nemotron_model, "nim")
    if provider == "meterless":
        s.require("meterless_api_key")
        client = OpenAI(base_url=s.meterless_base_url, api_key=s.meterless_api_key, timeout=180,
                        default_headers={"meterless-app": s.meterless_app_id})
        return LLMTarget(client, s.meterless_model, "meterless", {"meterless-scope": "user"})
    raise MissingSetting("Set NVIDIA_NIM_API_KEY (+ NEMOTRON_MODEL) or METERLESS_API_KEY in .env")
