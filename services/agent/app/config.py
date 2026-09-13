from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    internal_api_secret: str = Field(min_length=32)
    database_url: str = "postgresql://riverline:local-development-only@127.0.0.1:15432/riverline"
    daily_api_key: str = ""
    elevenlabs_api_key: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    stt_model: str = "scribe_v2_realtime"
    tts_model: str = "eleven_turbo_v2_5"
    # Luna's tool-calling proved unreliable in live calls: repeated malformed function-call
    # JSON, occasional unrecovered stalls, and one call-ending JSONDecodeError from its
    # streamed response. Terra trades some turn latency for correctness here.
    voice_model: str = "openai/gpt-5.6-terra"
    realtime_model: str = "gpt-realtime-2.1-mini"
    realtime_voice: str = "alloy"
    # Which voice engine actually runs. The cascade (STT -> LLM -> TTS, own turn
    # detection) and the realtime speech-to-speech engine share every tool, prompt,
    # session, and tracing concern; only this flag and which pipeline module main.py
    # imports differ. Flip it back to "cascade" without touching any other code.
    voice_engine: Literal["cascade", "realtime"] = "realtime"
    voice_max_sessions: int = Field(default=2, ge=1, le=10)
    voice_max_seconds: int = Field(default=900, ge=60, le=1800)
    model_config = SettingsConfigDict(extra="ignore")

    @property
    def voice_ready(self) -> bool:
        if not self.daily_api_key:
            return False
        if self.voice_engine == "realtime":
            return bool(self.openai_api_key)
        return bool(self.elevenlabs_api_key and self.openrouter_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
