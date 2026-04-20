from __future__ import annotations

from fastmcp import FastMCP

from app.workflows.orchestrator import SendWorkflowOrchestrator

mcp = FastMCP("email-mcp")

_orch: SendWorkflowOrchestrator | None = None


def _orchestrator() -> SendWorkflowOrchestrator:
    global _orch
    if _orch is None:
        _orch = SendWorkflowOrchestrator.from_settings()
    return _orch


@mcp.tool()
def resolve_recipients(names: list[str]) -> dict:
    """Resolve names or emails to employees (DB directory when registry is on): returns email + profile."""
    return _orchestrator().resolve_recipients(names)


@mcp.tool()
def employee_list(limit: int = 200) -> dict:
    """List active employees (name, email, profile: data_science, java, ui, devops, ...)."""
    return _orchestrator().employee_list(limit=limit)


@mcp.tool()
def employee_add(full_name: str, email: str, profile: str) -> dict:
    """Add a colleague to the directory so they can receive mail and appear in resolve_recipients."""
    return _orchestrator().employee_add(full_name, email, profile)


@mcp.tool()
def employee_deactivate(email: str) -> dict:
    """Soft-remove an employee from the directory (they can no longer be recipients)."""
    return _orchestrator().employee_deactivate(email)


@mcp.tool()
def exemplar_list() -> dict:
    """List RAG email exemplars stored in the database (formats for drafting)."""
    return _orchestrator().exemplar_list()


@mcp.tool()
def exemplar_add(
    format_kind: str,
    title: str,
    body_text: str,
    profile: str | None = None,
) -> dict:
    """Add an email format/template to the DB; call reload_rag_from_exemplar_tables to re-embed."""
    return _orchestrator().exemplar_add(format_kind, title, body_text, profile=profile)


@mcp.tool()
def reload_rag_from_exemplar_tables() -> dict:
    """Rebuild in-memory RAG index from DB exemplars (+ optional JSONL corpus path)."""
    return _orchestrator().reload_rag_from_exemplar_tables()


@mcp.tool()
def rag_status() -> dict:
    """Counts indexed chunks and shows RAG configuration (mode, top_k, persist path)."""
    return _orchestrator().rag_status()


@mcp.tool()
def rag_ingest_documents(documents: list[dict]) -> dict:
    """Upsert exemplar chunks. Each item: text (required), optional topic/intent/team/id/metadata."""
    return _orchestrator().rag_ingest_documents(documents)


@mcp.tool()
def rag_search(
    query: str,
    k: int = 5,
    topic: str | None = None,
    intent: str | None = None,
    team: str | None = None,
) -> dict:
    """Debug retrieval: run similarity search with optional metadata filters."""
    return _orchestrator().rag_search(query, k=k, topic=topic, intent=intent, team=team)


@mcp.tool()
def read_gmail_thread(gmail_thread_id: str) -> dict:
    """Fetch a Gmail thread by provider id. Uses the real Gmail API when EMAIL_MCP_USE_STUB_GMAIL=false."""
    return _orchestrator().read_gmail_thread(gmail_thread_id)


@mcp.tool()
def read_thread_stub(thread_id: str) -> dict:
    """Backward-compatible alias for read_gmail_thread."""
    return _orchestrator().read_gmail_thread(thread_id)


@mcp.tool()
def start_email_send(
    to: list[str],
    topic: str | None = None,
    instruction: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict:
    """Start the send workflow: validates allowlist, builds a draft (model + RAG stub), pauses at human approval."""
    result = _orchestrator().start_send(
        to=to,
        cc=cc,
        bcc=bcc,
        topic=topic,
        instruction=instruction,
    )
    if result.error:
        return {"thread_id": result.thread_id, "error": result.error}
    return {"thread_id": result.thread_id, "pending_approval": result.pending}


@mcp.tool()
def get_workflow_status(thread_id: str) -> dict:
    """Return persisted draft row (if any) and latest LangGraph checkpoint snapshot."""
    return _orchestrator().get_workflow_status(thread_id)


@mcp.tool()
def submit_approval(
    thread_id: str,
    action: str,
    approver_id: str,
    subject: str | None = None,
    body: str | None = None,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict:
    """Resume the workflow: action is approve (optionally edit fields) or cancel. Approve triggers stub/real Gmail send."""
    r = _orchestrator().submit_approval(
        thread_id=thread_id,
        action=action,
        approver_id=approver_id,
        subject=subject,
        body=body,
        to=to,
        cc=cc,
        bcc=bcc,
    )
    out: dict = {"thread_id": r.thread_id}
    if r.error:
        out["error"] = r.error
    if r.cancelled:
        out["cancelled"] = True
    if r.provider_message_id:
        out["provider_message_id"] = r.provider_message_id
    if r.track_id:
        out["track_id"] = r.track_id
    return out


@mcp.tool()
def track_reply_status(track_id: str) -> dict:
    """Phase 4: poll Gmail thread and update reply status for a tracked send."""
    return _orchestrator().track_reply_status(track_id)


@mcp.tool()
def detect_no_response(track_id: str) -> dict:
    """Phase 4: refresh reply state; if SLA deadline passed and still no reply, mark `no_response`."""
    return _orchestrator().detect_no_response(track_id)


@mcp.tool()
def list_tracked_sends(limit: int = 50) -> dict:
    """Phase 4: recent outbound sends under SLA tracking."""
    return _orchestrator().list_tracked_sends(limit=limit)


@mcp.tool()
def stub_inject_gmail_reply(gmail_thread_id: str, from_email: str) -> dict:
    """Dev/test only (stub Gmail): append a synthetic inbound message to a thread."""
    return _orchestrator().stub_inject_gmail_reply(gmail_thread_id, from_email)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
