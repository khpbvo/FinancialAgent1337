from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def trace_context(workflow_name: str, group_id: str | None = None) -> Iterator[None]:
    # Placeholder: OpenAI Agents SDK tracing hooks are configured on Runner.run
    # This context manager is here to centralize any future tracing setup.
    yield

