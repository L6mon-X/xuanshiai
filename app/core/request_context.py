"""Request-scoped context values shared by API dependencies and services.

``current_user_id_context`` carries the authenticated user id of the request
currently being served.  It exists so that cross-cutting guards (for example
the AI test-scope guard below) can read the caller without threading the user
object through every service signature.

Only :func:`app.api.dependencies.get_current_user` writes it.  Background
workers and scripts never set it, so readers must tolerate ``None``.
"""

from __future__ import annotations

from contextvars import ContextVar

current_user_id_context: ContextVar[int | None] = ContextVar(
    "current_user_id", default=None
)
