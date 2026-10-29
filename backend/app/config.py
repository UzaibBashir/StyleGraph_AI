from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    qloo_api_key: str = ""
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    backend_mode: str = "demo"
    frontend_origins: str = "http://localhost:8501"
    max_upload_mb: int = 8
    model_name: str = "ViT-B-32"
    model_pretrained: str = "openai"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def mode(self) -> str:
        return "live" if self.backend_mode.lower() == "live" else "demo"


@lru_cache
def get_settings() -> Settings:
    return Settings()

