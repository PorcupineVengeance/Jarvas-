from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore", env_file=".env")

    manus_api_url: str | None = None
    manus_api_key: str | None = Field(default=None, repr=False)
    manus_project_id: str | None = None
    manus_jwt_secret: str | None = Field(default=None, repr=False)
    manus_oauth_portal_url: str | None = None
    manus_oauth_api_url: str | None = None
    database_url: str | None = Field(default=None, repr=False)
    jarvis_session_ttl_seconds: int = 28_800
    jarvis_max_upload_mb: int = 15
    jarvis_llm_api_url: str | None = None
    jarvis_llm_api_key: str | None = Field(default=None, repr=False)
    jarvis_llm_model: str | None = None
    jarvis_research_api_id: str | None = None
    jarvis_tts_api_url: str | None = None
    jarvis_tts_api_key: str | None = Field(default=None, repr=False)
    jarvis_tts_model: str | None = None
    jarvis_tts_voice: str = "alloy"
    jarvis_allowed_origins: str = ""

    @property
    def api_base(self) -> str | None:
        return self.manus_api_url.rstrip("/") if self.manus_api_url else None

    @property
    def manus_service_ready(self) -> bool:
        return bool(self.api_base and self.manus_api_key)

    @property
    def llm_api_base(self) -> str | None:
        if self.jarvis_llm_api_url:
            return self.jarvis_llm_api_url.rstrip("/")
        return self.api_base

    @property
    def llm_api_key(self) -> str | None:
        if self.jarvis_llm_api_url:
            return self.jarvis_llm_api_key
        return self.manus_api_key

    @property
    def llm_model(self) -> str | None:
        return self.jarvis_llm_model

    @property
    def llm_provider_name(self) -> str:
        return "OpenAI-compatible custom provider" if self.jarvis_llm_api_url else "Manus AI"

    @property
    def llm_ready(self) -> bool:
        if self.jarvis_llm_api_url:
            return bool(self.jarvis_llm_api_key and self.jarvis_llm_model)
        return self.manus_service_ready

    @property
    def llm_completion_url(self) -> str | None:
        base = self.llm_api_base
        if not base:
            return None
        return f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"

    @property
    def oauth_ready(self) -> bool:
        return bool(self.manus_project_id and self.manus_jwt_secret and self.manus_oauth_portal_url and self.manus_oauth_api_url)

    @property
    def transcription_ready(self) -> bool:
        return self.manus_service_ready

    @property
    def tts_ready(self) -> bool:
        return bool(self.jarvis_tts_api_url and self.jarvis_tts_api_key and self.jarvis_tts_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
