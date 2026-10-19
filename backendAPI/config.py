from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # signs the users' JWTs; HS256 wants at least 32 characters
    jwt_secret: str = Field(min_length=32)
    jwt_expiry_hours: int = 8
    # how long a pairing code from the dashboard stays valid
    pairing_code_minutes: int = Field(default=10, ge=1, le=60)
    # the compost stage classifier (see stage_model.py). ml_dir is its code
    # (predict.py, features.py); the model and its parameters are files, so
    # either can be swapped without touching the code. Unset = the defaults
    ml_dir: Path = Path(__file__).resolve().parent.parent / "ml"
    stage_model_path: Path | None = None
    stage_model_params: Path | None = None

    # resolved from this file, so the API starts from any working directory
    model_config = SettingsConfigDict(env_file=Path(__file__).parent / ".env")


settings = Settings()
