from __future__ import annotations

from google.oauth2.credentials import Credentials

from app.config import Settings


def credentials_from_settings(settings: Settings) -> Credentials:
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_refresh_token:
        raise ValueError(
            "Real Gmail requires EMAIL_MCP_GOOGLE_CLIENT_ID, EMAIL_MCP_GOOGLE_CLIENT_SECRET, "
            "and EMAIL_MCP_GOOGLE_REFRESH_TOKEN"
        )
    return Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri=settings.google_token_uri,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=settings.gmail_oauth_scope_list(),
    )
