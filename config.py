from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    public_base_url: str = "http://localhost:8000"

    bank_name: str = "Cooperative Bank"
    bank_phone: str = ""

    call_start_hour: int = 9
    call_end_hour: int = 18
    max_call_attempts: int = 3

    database_url: str = "sqlite+aiosqlite:///./telecaller.db"


settings = Settings()
