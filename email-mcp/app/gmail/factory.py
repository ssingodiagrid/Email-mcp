from __future__ import annotations

from app.config import Settings
from app.gmail.client import GmailClient
from app.gmail.credentials import credentials_from_settings
from app.gmail.real_client import RealGmailClient
from app.gmail.stub import StubGmailClient


def build_gmail_client(settings: Settings) -> GmailClient:
    if settings.use_stub_gmail:
        return StubGmailClient(settings)
    creds = credentials_from_settings(settings)
    return RealGmailClient(settings, creds)
