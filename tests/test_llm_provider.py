"""Provider selection: Meterless Nightshift is the primary provider; NVIDIA NIM only when asked for."""
from __future__ import annotations

import pytest

from src.config import MissingSetting, Settings
from src.llm import build_llm, select_provider


def test_meterless_is_the_default_even_when_a_nim_key_is_set():
    s = Settings(meterless_api_key="tok", nvidia_nim_api_key="nvapi-x", nemotron_model="nvidia/nemotron")
    llm = build_llm(s)
    assert llm.provider == "meterless" and llm.model == "meterless/deep"
    assert str(llm.client.base_url).startswith("http://127.0.0.1:8088/v1")
    assert llm.chat_extra_headers == {"meterless-scope": "user"}


def test_meterless_model_is_configurable():
    llm = build_llm(Settings(meterless_api_key="tok", meterless_model="meterless/fast"))
    assert llm.model == "meterless/fast"


def test_nim_only_when_explicitly_selected():
    s = Settings(llm_provider="NIM", nvidia_nim_api_key="nvapi-x", nemotron_model="nvidia/nemotron")
    llm = build_llm(s)
    assert llm.provider == "nim" and llm.model == "nvidia/nemotron"


def test_missing_meterless_token_names_the_setting_and_the_fallback():
    with pytest.raises(MissingSetting, match="METERLESS_API_KEY.*LLM_PROVIDER=nim"):
        build_llm(Settings(nvidia_nim_api_key="nvapi-x", nemotron_model="nvidia/nemotron"))


def test_unknown_provider_is_rejected():
    with pytest.raises(MissingSetting):
        select_provider(Settings(llm_provider="openai"))
