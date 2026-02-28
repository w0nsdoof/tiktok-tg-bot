from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: SecretStr
    admin_user_ids: list[int] = []
    allowed_user_ids: list[int] = []
    max_duration: int = 300
    max_file_size: int = 50
    max_concurrent_downloads: int = 3
    download_dir: str = "/tmp/tg-bot-downloads"
    data_dir: str = "data"
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("allowed_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def parse_comma_separated_ids(cls, v: object) -> list[int]:
        if isinstance(v, list):
            return [int(i) for i in v]
        if isinstance(v, (str, int)):
            return [int(x.strip()) for x in str(v).split(",") if x.strip()]
        return []

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}
