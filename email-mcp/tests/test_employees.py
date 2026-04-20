from __future__ import annotations

import pytest

from app.config import Settings
from app.workflows.orchestrator import SendWorkflowOrchestrator


@pytest.fixture()
def orch(tmp_path):
    db = tmp_path / "a.db"
    cp = tmp_path / "c.sqlite"
    return SendWorkflowOrchestrator.from_settings(
        Settings(
            database_url=f"sqlite:///{db}",
            langgraph_checkpoint_path=str(cp),
            use_stub_gmail=True,
            seed_demo_data=True,
            require_employee_registry=True,
            rag_fallback_stub=False,
            rag_hydrate_from_db_exemplars=True,
        )
    )


def test_start_send_rejects_email_not_in_registry(orch: SendWorkflowOrchestrator):
    r = orch.start_send(to=["not.in.registry@griddynamics.com"], topic="t", instruction="i")
    assert r.error
    assert "not in employee directory" in r.error.lower() or "recipient policy" in r.error.lower()


def test_resolve_finds_by_email_and_name(orch: SendWorkflowOrchestrator):
    by_mail = orch.resolve_recipients(["sweeti@griddynamics.com"])
    assert by_mail["matches"][0]["candidates"]
    by_name = orch.resolve_recipients(["Sweeti"])
    assert by_name["matches"][0]["candidates"]
    assert by_name["matches"][0]["candidates"][0].get("profile") == "ui"


def test_submit_approval_rejects_unknown_cc(orch: SendWorkflowOrchestrator):
    start = orch.start_send(to=["siddharth@griddynamics.com"], topic="t", instruction="i")
    out = orch.submit_approval(
        thread_id=start.thread_id,
        action="approve",
        approver_id="x",
        subject=start.pending["subject"],
        body=start.pending["body"],
        to=start.pending["to"],
        cc=["nobody@griddynamics.com"],
    )
    assert out.error
