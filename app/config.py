from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8000
    log_level: str = "info"

    # LLM is optional — rules + templates work without any key.
    use_llm: bool = False
    llm_provider: str = "gemini"  # gemini | openai | none
    llm_timeout_seconds: float = 8.0

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @property
    def llm_enabled(self) -> bool:
        if not self.use_llm:
            return False
        if self.llm_provider == "gemini" and self.gemini_api_key.strip():
            return True
        if self.llm_provider == "openai" and self.openai_api_key.strip():
            return True
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
