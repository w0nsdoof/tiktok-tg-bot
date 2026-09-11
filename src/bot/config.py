from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: SecretStr
    database_dsn: SecretStr | None = None
    analytics_dsn: SecretStr | None = None
    admin_user_ids: list[int] = []
    allowed_user_ids: list[int] = []
    max_duration: int = 300
    max_file_size: int = 50
    max_concurrent_downloads: int = 3
    download_dir: str = "/tmp/tg-bot-downloads"
    instagram_cookies_file: str | None = None
    data_dir: str = "data"
    log_level: str = "INFO"
    log_json: bool = False
    control_panel_url: str | None = None
    web_session_secret: SecretStr | None = None
    web_session_max_age: int = 900
    authentik_issuer: str | None = None
    authentik_client_id: str | None = None
    authentik_client_secret: SecretStr | None = None
    authentik_operator_group: str = "tiktok-bot-operators"
    authentik_admin_group: str = "tiktok-bot-admins"

    @property
    def effective_database_dsn(self) -> str | None:
        dsn = self.database_dsn or self.analytics_dsn
        return dsn.get_secret_value() if dsn else None

    @field_validator("allowed_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def parse_comma_separated_ids(cls, v: object) -> list[int]:
        if isinstance(v, list):
            return [int(i) for i in v]
        if isinstance(v, (str, int)):
            return [int(x.strip()) for x in str(v).split(",") if x.strip()]
        return []

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}
