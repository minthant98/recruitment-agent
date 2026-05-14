from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",        # ← this is the key fix
    )

    # ── LLM ───────────────────────────────────────────
    groq_api_key: str
    groq_screener_model: str = "llama-3.1-8b-instant"
    groq_judge_model: str = "llama-3.3-70b-versatile"
    groq_screener_temperature: float = 0.0
    groq_judge_temperature: float = 0.3

    # ── Supabase ──────────────────────────────────────
    supabase_url: str
    supabase_service_key: str

    # ── Gmail ─────────────────────────────────────────
    gmail_credentials_path: str = "credentials/gmail_credentials.json"
    gmail_token_path: str = "credentials/gmail_token.json"
    recruitment_email_label: str = "recruitment"

    # ── HR Notification ───────────────────────────────
    hr_notification_email: str = ""

    # ── Pipeline thresholds ───────────────────────────
    auto_pass_threshold: float = Field(default=70.0, ge=0, le=100)
    auto_reject_threshold: float = Field(default=40.0, ge=0, le=100)

    # ── Audit ─────────────────────────────────────────
    audit_excel_path: str = "outputs/hr_audit.xlsx"

    # ── LangSmith Tracing ─────────────────────────────
    langsmith_tracing: str = "true"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "Recruitment Agent"

    # ── Logging ───────────────────────────────────────
    log_level: str = "INFO"
    
    # Auth
    SECRET_KEY: str = "change-this"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480


    # App
    APP_BASE_URL: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance. Call this everywhere."""
    return Settings()