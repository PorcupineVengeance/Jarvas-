from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / ".env",
        here.parents[3] / ".env",  # jarvisai/.env when running from backend/app
        here.parents[2] / ".env",
    ]
    return tuple(str(path) for path in candidates if path.is_file()) or (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore", env_file=_env_files(), env_file_encoding="utf-8")

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
    jarvis_stt_api_url: str | None = None
    jarvis_stt_api_key: str | None = Field(default=None, repr=False)
    jarvis_stt_model: str = "whisper-large-v3-turbo"
    jarvis_research_api_id: str | None = None
    jarvis_research_provider: str = "duckduckgo"
    jarvis_tavily_api_key: str | None = Field(default=None, repr=False)
    jarvis_tts_provider: str = "fish"
    jarvis_tts_api_url: str | None = None
    jarvis_tts_api_key: str | None = Field(default=None, repr=False)
    jarvis_tts_model: str | None = None
    jarvis_tts_voice: str = ""
    jarvis_allowed_origins: str = ""
    jarvis_open_access: bool = True
    jarvis_local_auth_enabled: bool = True
    jarvis_local_auth_secret: str | None = Field(default=None, repr=False)
    jarvis_local_auth_display_name: str = "Operator"
    jarvis_storage_dir: str = "./storage"
    jarvis_enable_computer_control: bool = False
    jarvis_allowed_paths: str = "~/Desktop,~/Documents,~/Downloads"
    jarvis_wake_word_enabled: bool = False
    jarvis_continuous_listening: bool = False

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
        if self.jarvis_llm_api_url:
            host = self.jarvis_llm_api_url.lower()
            if "groq.com" in host:
                return "Groq"
            if "openai.com" in host:
                return "OpenAI"
            return "OpenAI-compatible custom provider"
        return "Manus AI"

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
    def local_auth_ready(self) -> bool:
        return bool(self.jarvis_local_auth_enabled and self.session_local_secret)

    @property
    def session_local_secret(self) -> str | None:
        if self.jarvis_local_auth_secret and len(self.jarvis_local_auth_secret) >= 16:
            return self.jarvis_local_auth_secret
        # Open-access deploys (e.g. Vercel) can run without a configured secret.
        if self.jarvis_open_access:
            return "jarvis-open-access-fallback-secret"
        return None

    @property
    def auth_ready(self) -> bool:
        return self.oauth_ready or self.local_auth_ready or self.jarvis_open_access

    @property
    def session_signing_secret(self) -> str | None:
        if self.oauth_ready:
            return self.manus_jwt_secret
        return self.session_local_secret

    @property
    def resolved_database_url(self) -> str:
        on_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        url = (self.database_url or "").strip()
        # Vercel/serverless filesystems are read-only except /tmp — never use ./data there.
        if on_serverless and (not url or url.startswith("sqlite:")):
            return "sqlite:////tmp/jarvis.db"
        if url:
            return url
        return "sqlite:///./data/jarvis.db"

    @property
    def transcription_ready(self) -> bool:
        if self.jarvis_stt_api_url and self.jarvis_stt_api_key:
            return True
        return self.manus_service_ready

    @property
    def transcription_api_base(self) -> str | None:
        if self.jarvis_stt_api_url:
            return self.jarvis_stt_api_url.rstrip("/")
        return self.api_base

    @property
    def transcription_api_key(self) -> str | None:
        if self.jarvis_stt_api_url:
            return self.jarvis_stt_api_key
        return self.manus_api_key

    @property
    def tts_ready(self) -> bool:
        return bool(self.jarvis_tts_api_url and self.jarvis_tts_api_key and self.jarvis_tts_model)

    @property
    def research_ready(self) -> bool:
        provider = (self.jarvis_research_provider or "").lower()
        if provider == "duckduckgo":
            return True
        if provider == "tavily":
            return bool(self.jarvis_tavily_api_key)
        if provider == "manus":
            return bool(self.jarvis_research_api_id and self.manus_service_ready)
        return False

    @property
    def storage_path(self) -> Path:
        raw = self.jarvis_storage_dir
        if (os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")) and raw in {"./storage", "storage"}:
            path = Path("/tmp/jarvis-storage")
        else:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
        return path.resolve()

    @property
    def allowed_paths(self) -> list[Path]:
        paths: list[Path] = []
        for item in self.jarvis_allowed_paths.split(","):
            raw = item.strip()
            if not raw:
                continue
            paths.append(Path(raw).expanduser().resolve())
        return paths


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
