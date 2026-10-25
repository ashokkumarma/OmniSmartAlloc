"""Settings loaded from .env.local / .env (process env wins). No defaults for secrets."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent


class MissingSetting(RuntimeError):
    pass


class Settings(BaseModel):
    llm_provider: str = ""
    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = ""
    meterless_api_key: str = ""
    meterless_base_url: str = "http://127.0.0.1:8088/v1"
    meterless_app_id: str = "open-agent-hackathon"
    meterless_model: str = "meterless/auto"
    zetaris_jdbc_url: str = ""
    zetaris_jdbc_jar: str = ""
    zetaris_username: str = ""
    zetaris_password: str = ""
    agent_max_steps: int = 8
    agent_max_rows: int = 50

    def require(self, *fields: str) -> None:
        missing = [f.upper() for f in fields if not getattr(self, f)]
        if missing:
            raise MissingSetting(f"Set {', '.join(missing)} in .env (see .env.example)")


@lru_cache
def get_settings() -> Settings:
    for name in (".env.local", ".env"):
        if (ROOT / name).is_file():
            load_dotenv(ROOT / name, override=False)
    values = {k: os.environ[k.upper()].strip() for k in Settings.model_fields if os.environ.get(k.upper(), "").strip()}
    return Settings(**values)
