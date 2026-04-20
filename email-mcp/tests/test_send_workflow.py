from __future__ import annotations

import pytest

from app.config import Settings
from app.storage.models import DraftStatus
from app.workflows.orchestrator import SendWorkflowOrchestrator


@pytest.fixture()
def orch(tmp_path):
    db = tmp_path / "app.db"
    cp = tmp_path / "checkpoint.sqlite"
    settings = Settings(
        database_url=f"sqlite:///{db}",
        langgraph_checkpoint_path=str(cp),
        allowed_email_domains="griddynamics.com",
        allow_subdomains=True,
        use_stub_gmail=True,
    )
    return SendWorkflowOrchestrator.from_settings(settings)


def test_validation_failure_persists_failed_draft(orch: SendWorkflowOrchestrator):
    r = orch.start_send(to=["evil@gmail.com"], topic="t", instruction="i")
    assert r.error
    st = orch.get_workflow_status(r.thread_id)
    assert st["database"]["status"] == DraftStatus.FAILED_VALIDATION.value


def test_happy_path_requires_approval_before_send(orch: SendWorkflowOrchestrator):
    start = orch.start_send(
        to=["siddharth@griddynamics.com"],
        topic="Rollout",
        instruction="Share timeline",
    )
    assert start.pending
    assert "subject" in start.pending

    out = orch.submit_approval(
        thread_id=start.thread_id,
        action="approve",
        approver_id="reviewer-1",
        subject=start.pending["subject"],
        body=start.pending["body"],
        to=start.pending["to"],
    )
    assert out.provider_message_id
    assert out.provider_message_id.startswith("stub:")

    st = orch.get_workflow_status(start.thread_id)
    assert st["database"]["status"] == DraftStatus.SENT.value


def test_cancel_does_not_send(orch: SendWorkflowOrchestrator):
    start = orch.start_send(to=["siddharth@griddynamics.com"], topic="t", instruction="i")
    out = orch.submit_approval(thread_id=start.thread_id, action="cancel", approver_id="reviewer-1")
    assert out.cancelled is True
    assert out.provider_message_id is None
    st = orch.get_workflow_status(start.thread_id)
    assert st["database"]["status"] == DraftStatus.CANCELLED.value


def test_approve_rejects_non_allowlisted_edit(orch: SendWorkflowOrchestrator):
    start = orch.start_send(to=["siddharth@griddynamics.com"], topic="t", instruction="i")
    out = orch.submit_approval(
        thread_id=start.thread_id,
        action="approve",
        approver_id="reviewer-1",
        to=["nope@gmail.com"],
    )
    assert out.error
