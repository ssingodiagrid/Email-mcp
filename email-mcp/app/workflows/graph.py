from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.employees.registry import EmployeeRegistry
from app.gmail.client import GmailClient
from app.policy.recipient_policy import RecipientPolicy
from app.rag.retrieval import RagRetriever


class EmailWorkflowState(TypedDict, total=False):
    thread_id: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    topic: str | None
    instruction: str | None
    subject: str
    body: str
    rag_snippets: list[str]
    error: str | None
    cancelled: bool
    provider_message_id: str | None


def build_send_workflow(
    policy: RecipientPolicy,
    rag: RagRetriever,
    gmail: GmailClient,
    checkpointer: BaseCheckpointSaver,
    *,
    rag_top_k: int = 3,
    employee_registry: EmployeeRegistry | None = None,
):
    def validate_recipients(state: EmailWorkflowState) -> dict:
        try:
            policy.ensure_allowed(
                state.get("to", []),
                state.get("cc", []) or [],
                state.get("bcc", []) or [],
            )
            if employee_registry is not None:
                employee_registry.ensure_recipients_registered(
                    state.get("to", []),
                    state.get("cc", []) or [],
                    state.get("bcc", []) or [],
                )
        except PermissionError as e:
            return {"error": str(e)}
        return {}

    def route_after_validate(state: EmailWorkflowState) -> str:
        return "failed" if state.get("error") else "ok"

    def build_draft(state: EmailWorkflowState) -> dict:
        snippets = rag.retrieve_exemplars(
            state.get("topic"),
            k=rag_top_k,
            instruction=state.get("instruction"),
        )
        topic = state.get("topic") or "Update"
        hint = state.get("instruction") or ""
        subject = topic if len(topic) <= 120 else topic[:117] + "..."
        body_lines = [
            "Hi,",
            "",
            f"(Draft proposal — requires human approval before sending. Hint: {hint})",
            "",
        ]
        for s in snippets:
            body_lines.append(f"Style reference: {s}")
            body_lines.append("")
        body_lines.extend(["Thanks,", "Email MCP (draft)"])
        body = "\n".join(body_lines)
        return {"subject": subject, "body": body, "rag_snippets": snippets}

    def human_approval(state: EmailWorkflowState) -> dict:
        payload = {
            "thread_id": state["thread_id"],
            "to": list(state.get("to", [])),
            "cc": list(state.get("cc", []) or []),
            "bcc": list(state.get("bcc", []) or []),
            "subject": state.get("subject", ""),
            "body": state.get("body", ""),
            "rag_snippets": list(state.get("rag_snippets", []) or []),
        }
        decision = interrupt(payload)
        if not isinstance(decision, dict):
            return {"cancelled": True}
        if decision.get("action") == "cancel":
            return {"cancelled": True}
        return {
            "cancelled": False,
            "subject": decision.get("subject", state.get("subject", "")),
            "body": decision.get("body", state.get("body", "")),
            "to": list(decision.get("to", state.get("to", []))),
            "cc": list(decision.get("cc", state.get("cc", []) or [])),
            "bcc": list(decision.get("bcc", state.get("bcc", []) or [])),
        }

    def route_after_human(state: EmailWorkflowState) -> str:
        return "end" if state.get("cancelled") else "send"

    def send_message(state: EmailWorkflowState) -> dict:
        policy.ensure_allowed(
            state.get("to", []),
            state.get("cc", []) or [],
            state.get("bcc", []) or [],
        )
        if employee_registry is not None:
            employee_registry.ensure_recipients_registered(
                state.get("to", []),
                state.get("cc", []) or [],
                state.get("bcc", []) or [],
            )
        mid = gmail.send_message(
            subject=state["subject"],
            body=state["body"],
            to=list(state["to"]),
            cc=list(state.get("cc", []) or []),
            bcc=list(state.get("bcc", []) or []),
        )
        return {"provider_message_id": mid}

    g = StateGraph(EmailWorkflowState)
    g.add_node("validate_recipients", validate_recipients)
    g.add_node("build_draft", build_draft)
    g.add_node("human_approval", human_approval)
    g.add_node("send_message", send_message)

    g.add_edge(START, "validate_recipients")
    g.add_conditional_edges(
        "validate_recipients",
        route_after_validate,
        {"failed": END, "ok": "build_draft"},
    )
    g.add_edge("build_draft", "human_approval")
    g.add_conditional_edges(
        "human_approval",
        route_after_human,
        {"end": END, "send": "send_message"},
    )
    g.add_edge("send_message", END)

    return g.compile(checkpointer=checkpointer)
