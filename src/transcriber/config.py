"""Settings, from the environment (and a .env in the working directory)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: SecretStr | None = None
    transcriber_openai_model: str = "gpt-4o-transcribe"
    # nexi's VM exposes a generic QEMU CPU without AVX2, where large-v3-turbo runs about
    # 4x slower than real time; small keeps up (~1x). Set large-v3-turbo on a better CPU.
    transcriber_local_model: str = "small"
    transcriber_cpu_threads: int = 4
    transcriber_host: str = "127.0.0.1"
    transcriber_port: int = 8090
    # Only files under this directory may be transcribed.
    transcriber_allowed_root: Path = Path.home()


@lru_cache
def get_settings() -> Settings:
    return Settings()
