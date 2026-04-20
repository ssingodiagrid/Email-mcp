"""
Reply tracking & SLA (Phase 4).

**Scheduling:** This service is synchronous MCP/API-driven. Run `track_reply_status` / `detect_no_response`
from your gateway on a timer (cron, Cloud Scheduler, Celery beat, or Java `@Scheduled`), or poll from
the Chrome extension when the user opens a view. A dedicated background worker is optional and can be
added later without changing the persistence model.
"""

from app.replies.tracker import ReplyTracker

__all__ = ["ReplyTracker"]
