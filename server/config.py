from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 서버
    host: str = "0.0.0.0"
    port: int = 8000

    # 인증
    api_keys: str = ""  # 콤마로 구분된 API 키 목록

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Rate Limiting
    rate_limit: str = "60/minute"

    # 기본 모델
    default_chat_model: str = "deepseek-coder-v2:16b"
    default_embed_model: str = "nomic-embed-text"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def api_key_list(self) -> list[str]:
        """API 키 목록 반환"""
        if not self.api_keys:
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
