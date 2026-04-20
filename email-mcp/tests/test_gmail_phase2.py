from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials

from app.config import Settings
from app.gmail.factory import build_gmail_client
from app.gmail.real_client import RealGmailClient
from app.workflows.orchestrator import SendWorkflowOrchestrator


def test_build_real_gmail_requires_credentials(tmp_path):
    db = tmp_path / "a.db"
    cp = tmp_path / "c.sqlite"
    settings = Settings(
        database_url=f"sqlite:///{db}",
        langgraph_checkpoint_path=str(cp),
        use_stub_gmail=False,
    )
    with pytest.raises(ValueError, match="GOOGLE"):
        build_gmail_client(settings)


def test_orchestrator_wraps_missing_oauth(tmp_path):
    db = tmp_path / "a.db"
    cp = tmp_path / "c.sqlite"
    settings = Settings(
        database_url=f"sqlite:///{db}",
        langgraph_checkpoint_path=str(cp),
        use_stub_gmail=False,
    )
    with pytest.raises(ValueError, match="USE_STUB_GMAIL"):
        SendWorkflowOrchestrator.from_settings(settings)


def test_real_client_send_calls_messages_api(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'a.db'}",
        langgraph_checkpoint_path=str(tmp_path / "c.sqlite"),
        google_client_id="id",
        google_client_secret="secret",
        google_refresh_token="refresh",
    )
    creds = Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri=settings.google_token_uri,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=settings.gmail_oauth_scope_list(),
    )
    client = RealGmailClient(settings, creds)
    mock_svc = MagicMock()
    send = mock_svc.users.return_value.messages.return_value.send
    send.return_value.execute.return_value = {"id": "msg-real-1"}
    with patch.object(client, "_api", return_value=mock_svc):
        mid = client.send_message(
            subject="S",
            body="B",
            to=["a@griddynamics.com"],
            cc=[],
            bcc=[],
        )
    assert mid == "msg-real-1"
    send.assert_called_once()


@pytest.mark.skipif(
    not __import__("os").environ.get("EMAIL_MCP_INTEGRATION"),
    reason="Set EMAIL_MCP_INTEGRATION=1 and Gmail OAuth env vars to run",
)
def test_integration_list_threads_smoke():
    s = Settings(use_stub_gmail=False)
    service = __import__("googleapiclient.discovery", fromlist=["build"]).build(
        "gmail", "v1", credentials=Credentials(
            token=None,
            refresh_token=s.google_refresh_token,
            token_uri=s.google_token_uri,
            client_id=s.google_client_id,
            client_secret=s.google_client_secret,
            scopes=s.gmail_oauth_scope_list(),
        ), cache_discovery=False
    )
    resp = service.users().threads().list(userId="me", maxResults=1).execute()
    assert isinstance(resp, dict)
