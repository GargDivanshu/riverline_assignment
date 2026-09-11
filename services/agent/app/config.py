from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    internal_api_secret: str = Field(min_length=32)
    database_url: str = "postgresql://riverline:local-development-only@127.0.0.1:15432/riverline"
    daily_api_key: str = ""
    elevenlabs_api_key: str = ""
    openrouter_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    stt_model: str = "scribe_v2_realtime"
    tts_model: str = "eleven_turbo_v2_5"
    # The spoken loop needs low turn latency. A deeper planning model can be added separately.
    voice_model: str = "openai/gpt-5.6-luna"
    voice_max_sessions: int = Field(default=2, ge=1, le=10)
    voice_max_seconds: int = Field(default=900, ge=60, le=1800)
    model_config = SettingsConfigDict(extra="ignore")

    @property
    def voice_ready(self) -> bool:
        return bool(self.daily_api_key and self.elevenlabs_api_key and self.openrouter_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
