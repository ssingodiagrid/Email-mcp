from __future__ import annotations

from app.config import Settings
from app.workflows.orchestrator import SendWorkflowOrchestrator


def _orch(tmp_path, **kwargs):
    db = tmp_path / "a.db"
    cp = tmp_path / "c.sqlite"
    settings = Settings(
        database_url=f"sqlite:///{db}",
        langgraph_checkpoint_path=str(cp),
        use_stub_gmail=True,
        **kwargs,
    )
    return SendWorkflowOrchestrator.from_settings(settings)


def test_track_id_after_approve_and_reply_detected(tmp_path):
    orch = _orch(tmp_path)
    start = orch.start_send(to=["siddharth@griddynamics.com"], topic="t", instruction="i")
    out = orch.submit_approval(
        thread_id=start.thread_id,
        action="approve",
        approver_id="rev",
        subject=start.pending["subject"],
        body=start.pending["body"],
        to=start.pending["to"],
    )
    assert out.track_id
    snap = orch.track_reply_status(out.track_id)
    assert snap["status"] == "awaiting_reply"
    assert snap["gmail_thread_id"]
    orch.stub_inject_gmail_reply(snap["gmail_thread_id"], "siddharth@griddynamics.com")
    snap2 = orch.track_reply_status(out.track_id)
    assert snap2["status"] == "replied"
    assert snap2.get("reply_from")


def test_no_response_when_sla_passed(tmp_path):
    orch = _orch(tmp_path, reply_sla_hours=-1.0)
    start = orch.start_send(to=["siddharth@griddynamics.com"], topic="t", instruction="i")
    out = orch.submit_approval(
        thread_id=start.thread_id,
        action="approve",
        approver_id="rev",
        subject=start.pending["subject"],
        body=start.pending["body"],
        to=start.pending["to"],
    )
    res = orch.detect_no_response(out.track_id)
    assert res.get("no_response") is True
    assert res["status"] == "no_response"
    listed = orch.list_tracked_sends(limit=5)
    assert len(listed["items"]) >= 1
