from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMAIL_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/app.db"
    langgraph_checkpoint_path: str = "./data/langgraph_checkpoint.sqlite"
    allowed_email_domains: str = "griddynamics.com"
    allow_subdomains: bool = True
    use_stub_gmail: bool = True

    # Phase 2 — user OAuth (refresh token from one-time consent; store via vault in production).
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None
    google_token_uri: str = "https://oauth2.googleapis.com/token"
    gmail_user_id: str = "me"
    google_oauth_scopes: str = (
        "https://www.googleapis.com/auth/gmail.send,"
        "https://www.googleapis.com/auth/gmail.readonly"
    )

    # Phase 3 — RAG (in-memory vector + deterministic embeddings by default).
    rag_mode: str = "vector"  # vector | stub
    rag_top_k: int = 3
    rag_embedding_dim: int = 256
    rag_fallback_stub: bool = True
    rag_corpus_path: str | None = None  # JSONL of {text, topic?, intent?, team?, id?, metadata?}
    rag_store_path: str | None = None  # e.g. ./data/rag_store.json to load/save embedded corpus

    # Phase 4 — reply / SLA (poll from gateway or scheduler).
    reply_sla_hours: float = 48.0
    mailbox_address: str | None = None  # defaults to Gmail profile email when using real API

    # Employee directory + RAG exemplars in SQLite (no OAuth for directory).
    require_employee_registry: bool = True
    seed_demo_data: bool = True
    rag_hydrate_from_db_exemplars: bool = True

    @field_validator("allowed_email_domains", mode="before")
    @classmethod
    def strip_domains(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    def domain_list(self) -> list[str]:
        parts = [p.strip().lower() for p in self.allowed_email_domains.split(",")]
        return [p for p in parts if p]

    def gmail_oauth_scope_list(self) -> list[str]:
        return [s.strip() for s in self.google_oauth_scopes.split(",") if s.strip()]


def get_settings() -> Settings:
    return Settings()
